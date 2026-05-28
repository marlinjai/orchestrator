import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient
from rich.console import Console

from orchestrator.config import MarlinProxyConfig, apply_task_overrides, load_config
from orchestrator.guardrails import (
    iteration_cap_hit,
    kill_switch_active,
    wall_clock_cap_hit,
)
from orchestrator.ledger import LedgerEntry, append_decision, append_note, now_iso
from orchestrator.marlin_proxy import MarlinDecision, run_marlin_decision
from orchestrator.parse import parse_frontmatter
from orchestrator.proxy import ProxyDecision, run_proxy_decision
from orchestrator.reconcile import git_head, reconcile
from orchestrator.state import IterationUsage, State, load_state, save_state
from orchestrator.transcript import AssistantTurn, extract_model, extract_text, extract_usage
from orchestrator.worker import build_worker_options, run_worker_turn


_BUNDLED_MARLIN_PERSONA = Path(__file__).parent.parent / "personas" / "marlin.md"


@dataclass
class OrchestratorConfig:
    task_id: str
    goal_file: Path
    persona_file: Path
    project_dir: Path
    state_dir: Path
    max_iterations: int = 50
    max_seconds: float = 4 * 3600
    transcript_window: int = 10
    log_path: Path | None = None
    marlin_persona_file: Path | None = None


console = Console()


class _TeeStream(io.TextIOBase):
    """Write text to multiple underlying streams.

    Used to tee Console output to both stdout and a run.log file so that
    `orchestrator logs --task-id X` has something to read.
    """

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> int:
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                # Never let logging break the orchestrator loop.
                pass
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        # Force rich to render without ANSI escapes when teeing to a file,
        # so the log stays readable. Even though stdout may be a tty, rich
        # uses this to decide formatting on the Console wrapping the tee.
        return False


def _initialize_state(cfg: OrchestratorConfig) -> State:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    state_path = cfg.state_dir / "state.json"
    if state_path.exists():
        return load_state(state_path)
    goal = cfg.goal_file.read_text().strip()
    state = State(task_id=cfg.task_id, goal=goal, max_iterations=cfg.max_iterations)
    save_state(state_path, state)
    return state


async def _run_one_turn(
    *,
    client: ClaudeSDKClient,
    user_message: str,
    persona: str,
    state: State,
    transcript_window: int,
    out_console: Console | None = None,
) -> tuple[list[str], ProxyDecision, IterationUsage]:
    out = out_console or console
    chunks: list[str] = []
    usage = IterationUsage(iteration=state.iteration)
    worker_start = time.monotonic()
    async for msg in run_worker_turn(client=client, user_message=user_message):
        text = extract_text(msg)
        if text:
            chunks.append(text)
            out.print(f"[dim]worker:[/dim] {text}", end="")
        u = extract_usage(msg)
        if u:
            usage.input_tokens += int(u.get("input_tokens", 0) or 0)
            usage.output_tokens += int(u.get("output_tokens", 0) or 0)
            usage.cache_read_tokens += int(u.get("cache_read_input_tokens", 0) or 0)
            usage.cache_creation_tokens += int(u.get("cache_creation_input_tokens", 0) or 0)
        if not usage.model:
            m = extract_model(msg)
            if m:
                usage.model = m
    usage.worker_ms = int((time.monotonic() - worker_start) * 1000)
    recent = [AssistantTurn(text=t) for t in chunks if t.strip()][-transcript_window:]
    proxy_start = time.monotonic()
    decision = await run_proxy_decision(
        persona=persona,
        state=state,
        recent_turns=recent,
    )
    usage.proxy_ms = int((time.monotonic() - proxy_start) * 1000)
    return chunks, decision, usage


def _load_marlin(cfg: OrchestratorConfig, goal_text: str) -> tuple[MarlinProxyConfig, str]:
    """Resolve the Marlin Proxy config (global config + per-task frontmatter)
    and its persona text. If the proxy is enabled but the persona is missing,
    force mode=off so the orchestrator fails safe to plain escalation.
    """
    mp_config = load_config()
    frontmatter = parse_frontmatter(goal_text)
    mp_config = apply_task_overrides(mp_config, frontmatter)

    if mp_config.mode == "off":
        return mp_config, ""

    persona_path = cfg.marlin_persona_file or _BUNDLED_MARLIN_PERSONA
    if not persona_path.exists():
        mp_config.mode = "off"
        return mp_config, ""
    return mp_config, persona_path.read_text().strip()


def _record_marlin_decision(
    *,
    config: MarlinProxyConfig,
    state: State,
    marlin: MarlinDecision,
    tokens_in: int,
    wall_ms: int,
    iter_ms: int,
) -> None:
    """Update autonomy stats and append to the ledger (+ notes on auto-actions).
    A shadow-mode decision is logged with executed=False and its would-be choice
    preserved, so the weekly review can compute agreement against Marlin's later
    real choice (filled in out of band)."""
    stats = state.autonomy_stats
    if marlin.executed and marlin.choice == "auto_approve":
        stats.decisions_between_escalations += 1
        stats.max_decisions_between_escalations = max(
            stats.max_decisions_between_escalations,
            stats.decisions_between_escalations,
        )
        stats.autonomous_runtime_ms += iter_ms
        stats.auto_approved += 1
        append_note(
            config.notes_path,
            f"[{state.task_id} iter {state.iteration}] auto-approved "
            f"({marlin.category}): {marlin.reason}",
        )
    elif marlin.executed and marlin.choice == "auto_defer":
        stats.auto_deferred += 1
        append_note(
            config.notes_path,
            f"[{state.task_id} iter {state.iteration}] deferred "
            f"({marlin.category}): {marlin.reason}",
        )
    else:
        stats.escalated += 1
        stats.decisions_between_escalations = 0

    append_decision(
        config.ledger_path,
        LedgerEntry(
            ts=now_iso(),
            task_id=state.task_id,
            iteration=state.iteration,
            category=marlin.category,
            effective_mode=marlin.effective_mode,
            proxy_choice=marlin.proxy_choice,
            proxy_reason=marlin.reason,
            executed=marlin.executed,
            tokens_in=tokens_in,
            wall_ms=wall_ms,
        ),
    )


async def run_orchestrator(cfg: OrchestratorConfig) -> None:
    state = _initialize_state(cfg)
    state_path = cfg.state_dir / "state.json"
    persona = cfg.persona_file.read_text().strip()
    mp_config, marlin_persona = _load_marlin(cfg, state.goal)
    started_at = time.time()
    kill_switch = cfg.state_dir / "STOP"

    # Snapshot project HEAD before the Worker runs so reconciliation can detect
    # any commits the Worker makes but doesn't self-report. None if the project
    # isn't a git repo (reconciliation becomes a no-op).
    if state.baseline_ref is None:
        state.baseline_ref = git_head(cfg.project_dir)
        save_state(state_path, state)

    log_file = None
    if cfg.log_path is not None:
        cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = cfg.log_path.open("a", encoding="utf-8")
        tee = _TeeStream(sys.stdout, log_file)
        local_console = Console(file=tee, force_terminal=False)
    else:
        local_console = console

    try:
        if kill_switch_active(kill_switch):
            state.status = "stopped"
            state.exit_reason = "kill switch active before start"
            save_state(state_path, state)
            local_console.print("[red]kill switch active. exiting.[/red]")
            return

        initial_message = state.goal
        options = build_worker_options(
            state_path=state_path,
            project_dir=cfg.project_dir,
            denied_bash=[],
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                next_message = initial_message
                while True:
                    if iteration_cap_hit(iteration=state.iteration, max_iterations=cfg.max_iterations):
                        state.status = "stopped"
                        state.exit_reason = f"iteration cap reached ({cfg.max_iterations})"
                        save_state(state_path, state)
                        local_console.print(f"[yellow]{state.exit_reason}[/yellow]")
                        return
                    if wall_clock_cap_hit(started_at=started_at, max_seconds=cfg.max_seconds):
                        state.status = "stopped"
                        state.exit_reason = f"wall-clock cap reached ({cfg.max_seconds}s)"
                        save_state(state_path, state)
                        local_console.print(f"[yellow]{state.exit_reason}[/yellow]")
                        return
                    if kill_switch_active(kill_switch):
                        state.status = "stopped"
                        state.exit_reason = "kill switch activated"
                        save_state(state_path, state)
                        local_console.print("[red]kill switch activated. exiting.[/red]")
                        return

                    state.iteration += 1
                    save_state(state_path, state)
                    local_console.print(f"\n[bold cyan]=== iteration {state.iteration} ===[/bold cyan]")

                    chunks, decision, usage = await _run_one_turn(
                        client=client,
                        user_message=next_message,
                        persona=persona,
                        state=state,
                        transcript_window=cfg.transcript_window,
                        out_console=local_console,
                    )
                    local_console.print(f"\n[bold magenta]proxy:[/bold magenta] {decision.action} ({decision.reasoning})")

                    # Reload state (Worker may have appended via update_state),
                    # then reconcile against git and append usage. Persist once.
                    state = load_state(state_path)
                    state.usage.append(usage)
                    commits_added, files_added = reconcile(state, cfg.project_dir)
                    if commits_added or files_added:
                        local_console.print(
                            f"[dim]reconciled: +{commits_added} commits, +{files_added} files[/dim]"
                        )
                    save_state(state_path, state)
                    if decision.action == "stop":
                        state.status = "completed"
                        state.exit_reason = decision.reasoning or "proxy stopped"
                        save_state(state_path, state)
                        return
                    if decision.action == "escalate":
                        # The Decision Proxy wants Marlin. If the Marlin Proxy is
                        # enabled, let it try to answer on his behalf first.
                        if mp_config.mode == "off":
                            state.status = "escalated"
                            state.exit_reason = decision.text or decision.reasoning or "escalated"
                            save_state(state_path, state)
                            local_console.print(f"[bold red]ESCALATE:[/bold red] {decision.text}")
                            return

                        recent = [
                            AssistantTurn(text=t) for t in chunks if t.strip()
                        ][-cfg.transcript_window:]
                        escalation_text = decision.text or decision.reasoning or "escalated"
                        mp_start = time.monotonic()
                        marlin = await run_marlin_decision(
                            config=mp_config,
                            persona=marlin_persona,
                            state=state,
                            escalation_text=escalation_text,
                            recent_turns=recent,
                        )
                        mp_ms = int((time.monotonic() - mp_start) * 1000)
                        iter_ms = usage.worker_ms + usage.proxy_ms + mp_ms
                        _record_marlin_decision(
                            config=mp_config,
                            state=state,
                            marlin=marlin,
                            tokens_in=usage.input_tokens,
                            wall_ms=mp_ms,
                            iter_ms=iter_ms,
                        )
                        save_state(state_path, state)
                        local_console.print(
                            f"[bold blue]marlin-proxy:[/bold blue] {marlin.choice} "
                            f"[{marlin.category}/{marlin.effective_mode}] ({marlin.reason})"
                        )

                        if marlin.choice == "auto_approve":
                            next_message = (
                                f"Marlin approved: {marlin.reason}. Continue."
                            )
                            continue
                        if marlin.choice == "auto_defer":
                            state.status = "stopped"
                            state.exit_reason = f"deferred by marlin-proxy: {marlin.reason}"
                            save_state(state_path, state)
                            local_console.print(
                                f"[yellow]DEFERRED:[/yellow] {marlin.reason}"
                            )
                            return
                        # escalate (includes shadow mode, which always interrupts)
                        state.status = "escalated"
                        state.exit_reason = escalation_text
                        save_state(state_path, state)
                        local_console.print(f"[bold red]ESCALATE:[/bold red] {escalation_text}")
                        return
                    next_message = decision.text or "Continue."
        except Exception as e:
            state = load_state(state_path)
            state.status = "failed"
            state.exit_reason = f"sdk error: {type(e).__name__}: {e}"
            save_state(state_path, state)
            local_console.print(f"[bold red]SDK ERROR:[/bold red] {e}")
            raise
    finally:
        if log_file is not None:
            try:
                log_file.flush()
                log_file.close()
            except Exception:
                pass
