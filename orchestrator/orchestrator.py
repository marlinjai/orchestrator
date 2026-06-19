import asyncio
import io
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from claude_agent_sdk import ClaudeSDKClient
from rich.console import Console

from orchestrator.config import MarlinProxyConfig, apply_task_overrides, load_config
from orchestrator.guardrails import (
    DEFAULT_API_KEY_COST_CAP_USD,
    bash_allowed,
    cost_cap_hit,
    cumulative_tokens,
    estimate_cost_usd,
    iteration_cap_hit,
    kill_switch_active,
    usage_cap_hit,
    wall_clock_cap_hit,
)
from orchestrator.handover import (
    build_handover_prompt,
    is_handover_complete,
    seed_fresh_session_message,
    verify_handover_doc,
)
from orchestrator.held_out import decide_after_held_out
from orchestrator.ledger import LedgerEntry, append_decision, append_note, now_iso
from orchestrator.marlin_proxy import MarlinDecision, run_marlin_decision
from orchestrator.notify import TERMINAL_STATUSES, notify
from orchestrator.parse import parse_frontmatter
from orchestrator.proxy import ProxyDecision, run_proxy_decision
from orchestrator.reconcile import git_head, reconcile
from orchestrator.repo_registry import resolve_repo_policy
from orchestrator.retry import (
    MAX_TRANSIENT_RETRIES,
    backoff_delay,
    is_transient_sdk_error,
)
from orchestrator.stagnation import (
    DEFAULT_STAGNATION_STREAK_CAP,
    stagnation_hit,
    update_stagnation,
)
from orchestrator.state import (
    Handover,
    HeldOutRecord,
    IterationUsage,
    State,
    VerifyRecord,
    load_state,
    save_state,
)
from orchestrator.tamper import scan_tamper
from orchestrator.transcript import AssistantTurn, extract_model, extract_text, extract_usage
from orchestrator.usage_guard import (
    daily_cap_hit,
    global_kill_active,
    record_usage,
    tokens_in_window,
)
from orchestrator.verify import decide_after_verify, load_verify_config, run_verify
from orchestrator.worktree import (
    add_worktree,
    default_worktree_path,
    is_git_repo,
    remove_worktree,
    worktree_branch,
)
from orchestrator.worker import (
    AuthMode,
    apply_env_contract,
    build_worker_options,
    load_worker_extras,
    resolve_effective_mcp_servers,
    run_worker_turn,
)


logger = logging.getLogger(__name__)

_MAX_HANDOVER_LEGS = 10


class _HandoverSignal(Exception):
    """Raised inside the Worker loop to break out of the ClaudeSDKClient session
    and start a fresh one with the provided seed message."""

    def __init__(self, seed: str) -> None:
        self.seed = seed


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
    auth_mode: AuthMode = "subscription"
    max_cost_usd: float | None = None
    stagnation_streak_cap: int = DEFAULT_STAGNATION_STREAK_CAP
    # Per-run cumulative token ceiling (rate-limit runaway guard). None = off.
    max_tokens: int | None = None
    # Fleet-wide rolling 24h token budget across ALL runs on this home. None =
    # off. Operator-owned (env), never relaxable per task.
    daily_token_cap: int | None = None
    # Shared orchestrator home: holds the global STOP file + the usage ledger
    # that the daily cap sums over. Defaults to the env-resolved real home.
    orchestrator_home: Path = field(
        default_factory=lambda: Path(
            os.environ.get("ORCHESTRATOR_HOME", str(Path.home() / ".orchestrator"))
        )
    )
    # Operator-owned repo registry path. None = the default/env-resolved location
    # (see repo_registry._registry_path). Set explicitly in tests for isolation.
    repos_config: Path | None = None
    # Opt-in worktree-per-attempt isolation: run the Worker in its own git
    # worktree so a bad attempt is throwaway and the real checkout is untouched.
    # Default off = run in place (the historical behavior).
    worktree_isolation: bool = False
    # Operator-provided ad-hoc held-out command (the --held-out flag). Same trust
    # as the registry (operator-sourced, the goal file still cannot set it), but
    # for one-off / dogfood runs without a repos.toml entry. It can ADD a held-out
    # to a repo that has none; it can never weaken a registry-enforced one.
    held_out_override: str | None = None


console = Console()


def _resolve_auth_mode(cli_mode: AuthMode, frontmatter: dict) -> AuthMode:
    """Per-task frontmatter `auth_mode` (more specific) overrides the CLI default.
    An invalid value is ignored with a warning, falling back to the CLI mode."""
    raw = frontmatter.get("auth_mode")
    if raw is None:
        return cli_mode
    if raw in get_args(AuthMode):
        return raw  # type: ignore[return-value]
    logger.warning("goal frontmatter auth_mode=%r invalid; using %r", raw, cli_mode)
    return cli_mode


def _resolve_cost_cap(cli_cap: float | None, auth_mode: AuthMode) -> float | None:
    """An explicit --max-cost-usd always wins. Otherwise api_key runs get the
    protective default ceiling (metered tokens are real money); subscription runs
    get no enforced ceiling (per-token cost is notional there)."""
    if cli_cap is not None:
        return cli_cap if cli_cap > 0 else None
    if auth_mode == "api_key":
        return DEFAULT_API_KEY_COST_CAP_USD
    return None


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
    state: State,
    out_console: Console | None = None,
) -> tuple[list[str], IterationUsage]:
    """Run one Worker turn and return its text chunks + token usage.

    The Decision Proxy is intentionally NOT called here: the caller reloads and
    reconciles state against git first, then asks the Proxy, so the Proxy judges
    on machine ground truth rather than the Worker's (possibly incomplete)
    self-report.
    """
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
    return chunks, usage


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


async def _execute_handover(
    *,
    client: ClaudeSDKClient,
    handover_prompt: str,
    state: State,
    state_path: Path,
    cfg: OrchestratorConfig,
    work_dir: Path,
    persona: str,
    mp_config: MarlinProxyConfig,
    local_console: Console,
) -> str | None:
    """Send the handover prompt to the Worker, verify HANDOVER.md against git,
    record the handover in state, and return the fresh-session seed message.

    Returns None and sets state.status = "escalated" if the Worker fails to
    produce HANDOVER.md within one turn.
    """
    local_console.print("[bold yellow]handover:[/bold yellow] sending checkpoint prompt to Worker")
    state.iteration += 1
    save_state(state_path, state)

    handover_chunks, handover_usage = await _run_one_turn(
        client=client,
        user_message=handover_prompt,
        state=state,
        out_console=local_console,
    )
    worker_output = "".join(handover_chunks)

    # Reload + reconcile before checking the doc
    state = load_state(state_path)
    state.usage.append(handover_usage)
    # Count the handover turn's tokens toward the fleet-wide daily budget too,
    # so the global cap stays honest across multi-leg runs (the per-run cap
    # already sees it via state.usage).
    record_usage(
        cfg.orchestrator_home,
        task_id=cfg.task_id,
        iteration=state.iteration,
        tokens=(
            handover_usage.input_tokens
            + handover_usage.output_tokens
            + handover_usage.cache_read_tokens
            + handover_usage.cache_creation_tokens
        ),
    )
    reconcile(state, work_dir)
    save_state(state_path, state)

    doc_path = work_dir / "HANDOVER.md"

    if not is_handover_complete(worker_output) or not doc_path.exists():
        state.status = "escalated"
        missing = []
        if not is_handover_complete(worker_output):
            missing.append("HANDOVER_COMPLETE marker")
        if not doc_path.exists():
            missing.append("HANDOVER.md file")
        state.exit_reason = (
            f"handover failed: Worker did not produce {' or '.join(missing)}"
        )
        save_state(state_path, state)
        local_console.print(
            f"[bold red]HANDOVER FAILED:[/bold red] {state.exit_reason}"
        )
        return None

    discrepancies = verify_handover_doc(doc_path.read_text(), state, work_dir)
    if discrepancies:
        local_console.print(
            f"[yellow]handover: {len(discrepancies)} git discrepancy(s) noted in seed[/yellow]"
        )
        for d in discrepancies:
            local_console.print(f"[dim]  - {d}[/dim]")

    tokens = state.usage[-1].input_tokens if state.usage else 0
    state.handovers.append(
        Handover(
            at_turn=state.iteration,
            reason=f"context threshold ({tokens:,} tokens)",
            doc=str(doc_path),
        )
    )
    save_state(state_path, state)

    local_console.print(
        f"[bold yellow]handover:[/bold yellow] HANDOVER.md verified "
        f"(leg {len(state.handovers)}, {len(discrepancies)} discrepancies)"
    )
    # Fresh leg starts with a clean progress baseline so stagnation does not
    # carry across a successful handover (which is itself evidence of progress).
    state.stagnation_streak = 0
    state.last_progress_key = None
    save_state(state_path, state)
    return seed_fresh_session_message(doc_path, state, discrepancies)


async def run_orchestrator(cfg: OrchestratorConfig) -> None:
    state = _initialize_state(cfg)
    state_path = cfg.state_dir / "state.json"
    persona = cfg.persona_file.read_text().strip()
    mp_config, marlin_persona = _load_marlin(cfg, state.goal)
    goal_frontmatter = parse_frontmatter(state.goal)
    verify_config = load_verify_config(goal_frontmatter)
    worker_extras = load_worker_extras(goal_frontmatter)
    auth_mode = _resolve_auth_mode(cfg.auth_mode, goal_frontmatter)
    effective_cost_cap = _resolve_cost_cap(cfg.max_cost_usd, auth_mode)
    started_at = time.time()
    kill_switch = cfg.state_dir / "STOP"

    # Active tree all tree-touching ops key off (baseline, reconcile, verify,
    # tamper, held-out, Worker cwd). Defaults to the project; becomes a dedicated
    # worktree when isolation is on. Initialized here so the finally-block cleanup
    # is safe even if setup raises before the worktree is created.
    work_dir = cfg.project_dir
    worktree_active = False
    worktree_path: Path | None = None

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
        if global_kill_active(cfg.orchestrator_home):
            state.status = "stopped"
            state.exit_reason = "global kill switch active before start"
            save_state(state_path, state)
            local_console.print("[red]global kill switch active. exiting.[/red]")
            return

        # Operator-owned repo policy, resolved from the project's real git remote
        # (un-fakeable by the goal file). A malformed registry fails the run loud
        # rather than silently dropping a security field.
        try:
            policy = resolve_repo_policy(cfg.project_dir, cfg.repos_config)
        except ValueError as e:
            state.status = "failed"
            state.exit_reason = f"repo registry error: {e}"
            save_state(state_path, state)
            local_console.print(f"[bold red]repo registry error:[/bold red] {e}")
            return
        state.repo_remote = policy.remote
        # Held-out command resolution. The registry (keyed by the real remote)
        # ENFORCES one per repo and is never weakened by anything passed at
        # dispatch. When the repo has no registry held-out, an operator may supply
        # an ad-hoc one via --held-out (operator-sourced, same trust: a goal file
        # still cannot set it). A denylisted ad-hoc command fails the run loud.
        if policy.held_out_verify:
            state.held_out_verify = policy.held_out_verify
            held_out_source = "registry"
            if cfg.held_out_override:
                local_console.print(
                    "[yellow]--held-out ignored: this repo has an enforced "
                    "registry held_out_verify[/yellow]"
                )
        elif cfg.held_out_override:
            allowed, reason = bash_allowed(cfg.held_out_override)
            if not allowed:
                state.status = "failed"
                state.exit_reason = f"--held-out refused by denylist: {reason}"
                save_state(state_path, state)
                local_console.print(f"[bold red]{state.exit_reason}[/bold red]")
                return
            state.held_out_verify = cfg.held_out_override
            held_out_source = "cli"
        else:
            state.held_out_verify = None
            held_out_source = "none"
        state.stakes_tier = policy.stakes_tier
        save_state(state_path, state)
        local_console.print(
            f"[dim]repo policy: remote={policy.remote or '(none)'} "
            f"source={policy.source} stakes_tier={policy.stakes_tier} "
            f"held_out_verify={held_out_source}[/dim]"
        )

        # Worktree isolation (opt-in): run this attempt in its own git worktree so
        # a bad attempt is throwaway and the operator's checkout is untouched. A
        # non-git project cannot have worktrees, so it falls back to in-place with
        # a warning; a genuine git failure fails the run LOUD rather than silently
        # editing the real tree the operator asked to isolate.
        if cfg.worktree_isolation:
            if not is_git_repo(cfg.project_dir):
                local_console.print(
                    "[yellow]worktree isolation requested but project is not a git "
                    "repo; running in place[/yellow]"
                )
            else:
                wt_path = default_worktree_path(cfg.project_dir, cfg.task_id)
                branch = worktree_branch(cfg.task_id)
                try:
                    add_worktree(cfg.project_dir, wt_path, branch)
                except (RuntimeError, OSError) as e:
                    state.status = "failed"
                    state.exit_reason = f"worktree setup failed: {e}"
                    save_state(state_path, state)
                    local_console.print(
                        f"[bold red]worktree setup failed:[/bold red] {e}"
                    )
                    return
                work_dir = wt_path
                worktree_active = True
                worktree_path = wt_path
                local_console.print(
                    f"[dim]worktree: isolated attempt in {wt_path} on branch {branch}[/dim]"
                )

        # Snapshot the active tree's HEAD so reconciliation can detect commits the
        # Worker makes but does not self-report. None if not a git repo
        # (reconciliation becomes a no-op). Computed AFTER worktree setup so the
        # baseline is the worktree's, never the original's.
        if state.baseline_ref is None:
            state.baseline_ref = git_head(work_dir)
            save_state(state_path, state)

        if verify_config.command:
            local_console.print(
                f"[dim]verify gate: {verify_config.command} "
                f"(fix_cap={verify_config.fix_cap}, timeout={verify_config.timeout_s:.0f}s)[/dim]"
            )
        else:
            local_console.print(
                "[yellow]verify gate: no `verify` command in goal frontmatter; "
                "completion will NOT be build-verified[/yellow]"
            )

        cap_label = f"${effective_cost_cap:.2f}" if effective_cost_cap else "none"
        # Apply the env contract here too (idempotent: build_worker_options also
        # calls it) so the scrubbed var NAMES are auditable in run.log, per the
        # ROADMAP. Never logs values.
        scrubbed = apply_env_contract(auth_mode)
        scrub_label = f" | env scrubbed: {', '.join(scrubbed)}" if scrubbed else ""
        local_console.print(
            f"[dim]auth mode: {auth_mode} | cost cap: {cap_label}{scrub_label}[/dim]"
        )
        if auth_mode == "api_key":
            local_console.print(
                "[yellow]auth_mode=api_key: this run bills the metered Anthropic API "
                "(not the flat subscription). The cost cap is the guard.[/yellow]"
            )

        initial_message = state.goal
        if worker_extras.mcp_server_keys or worker_extras.allowed_tools:
            local_console.print(
                f"[dim]worker extras: mcp_servers={worker_extras.mcp_server_keys} "
                f"allowed_tools={worker_extras.allowed_tools}[/dim]"
            )
        # Enforce the per-repo MCP-server ceiling (operator-owned, un-fakeable).
        # Audit what the ceiling did to run.log; a goal can never enable a server
        # the operator did not allow for this repo (defaults always survive).
        if policy.allowed_mcp_servers is not None:
            _, dropped_servers = resolve_effective_mcp_servers(
                worker_extras.mcp_server_keys, policy.allowed_mcp_servers
            )
            local_console.print(
                f"[dim]mcp ceiling (repo policy): allowed={policy.allowed_mcp_servers} "
                f"| goal requested={worker_extras.mcp_server_keys or '[]'}"
                + (
                    f" | DROPPED (not in ceiling): {dropped_servers}"
                    if dropped_servers
                    else " | all within ceiling"
                )
                + "[/dim]"
            )
        options = build_worker_options(
            state_path=state_path,
            project_dir=work_dir,
            denied_bash=[],
            extras=worker_extras,
            auth_mode=auth_mode,
            allowed_mcp_servers=policy.allowed_mcp_servers,
        )

        next_message = initial_message
        leg = 0
        transient_retries = 0
        while leg < _MAX_HANDOVER_LEGS:
            try:
                async with ClaudeSDKClient(options=options) as client:
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
                        if global_kill_active(cfg.orchestrator_home):
                            state.status = "stopped"
                            state.exit_reason = "global kill switch activated (fleet-wide STOP)"
                            save_state(state_path, state)
                            local_console.print(
                                "[red]global kill switch active. exiting.[/red]"
                            )
                            return

                        state.iteration += 1
                        save_state(state_path, state)
                        local_console.print(f"\n[bold cyan]=== iteration {state.iteration} ===[/bold cyan]")

                        chunks, usage = await _run_one_turn(
                            client=client,
                            user_message=next_message,
                            state=state,
                            out_console=local_console,
                        )

                        # Reload state (Worker may have appended via update_state),
                        # then reconcile against git and append usage. Persist once.
                        state = load_state(state_path)
                        state.usage.append(usage)
                        commits_added, files_added = reconcile(state, work_dir)
                        if commits_added or files_added:
                            local_console.print(
                                f"[dim]reconciled: +{commits_added} commits, +{files_added} files[/dim]"
                            )

                        # Ask the Decision Proxy AFTER reconcile so it judges on
                        # machine ground truth (git + verify), never the Worker's
                        # self-report alone (the confirmed production failure: the
                        # Proxy saw commits:[] while the branch had commits). The
                        # recent turns go in as clearly fenced UNTRUSTED data so a
                        # Worker cannot inject a decision into the judge.
                        recent = [
                            AssistantTurn(text=t) for t in chunks if t.strip()
                        ][-cfg.transcript_window:]
                        proxy_start = time.monotonic()
                        decision = await run_proxy_decision(
                            persona=persona,
                            state=state,
                            recent_turns=recent,
                        )
                        usage.proxy_ms = int((time.monotonic() - proxy_start) * 1000)
                        local_console.print(f"\n[bold magenta]proxy:[/bold magenta] {decision.action} ({decision.reasoning})")

                        # Cost guard: record the running estimate every iteration
                        # (so subscription runs stay cost-aware), and stop before
                        # spending more once a dollar ceiling is set. The ceiling
                        # is auto-enabled in api_key mode, where tokens are real
                        # money; subscription runs pass max_usd=None and never trip.
                        state.estimated_cost_usd = estimate_cost_usd(state.usage)
                        if cost_cap_hit(
                            estimate_usd=state.estimated_cost_usd,
                            max_usd=effective_cost_cap,
                        ):
                            state.status = "stopped"
                            state.exit_reason = (
                                f"cost cap reached (~${state.estimated_cost_usd:.2f} "
                                f">= ${effective_cost_cap:.2f}, auth_mode={auth_mode})"
                            )
                            save_state(state_path, state)
                            local_console.print(f"[yellow]{state.exit_reason}[/yellow]")
                            return

                        # Usage guards (rate-limit runaway, not dollars: tokens
                        # are what the Anthropic quota meters even when billing is
                        # flat). Record this iteration's tokens to the shared
                        # fleet ledger, then enforce the per-run ceiling and the
                        # fleet-wide rolling daily budget. Both default off; the
                        # daily budget is operator-owned and un-promptable.
                        iter_tokens = (
                            usage.input_tokens
                            + usage.output_tokens
                            + usage.cache_read_tokens
                            + usage.cache_creation_tokens
                        )
                        record_usage(
                            cfg.orchestrator_home,
                            task_id=cfg.task_id,
                            iteration=state.iteration,
                            tokens=iter_tokens,
                        )
                        run_tokens = cumulative_tokens(state.usage)
                        if usage_cap_hit(total_tokens=run_tokens, max_tokens=cfg.max_tokens):
                            state.status = "stopped"
                            state.exit_reason = (
                                f"usage cap reached ({run_tokens:,} tokens "
                                f">= {cfg.max_tokens:,})"
                            )
                            save_state(state_path, state)
                            local_console.print(f"[yellow]{state.exit_reason}[/yellow]")
                            return
                        if cfg.daily_token_cap:
                            tokens_today = tokens_in_window(cfg.orchestrator_home)
                            if daily_cap_hit(
                                tokens_today=tokens_today, daily_cap=cfg.daily_token_cap
                            ):
                                state.status = "stopped"
                                state.exit_reason = (
                                    f"global daily token cap reached "
                                    f"({tokens_today:,} >= {cfg.daily_token_cap:,} "
                                    "in the last 24h across all runs)"
                                )
                                save_state(state_path, state)
                                local_console.print(f"[yellow]{state.exit_reason}[/yellow]")
                                return

                        # Stagnation brake: a Worker can burn the iteration cap
                        # thrashing on a failing verify or looping in
                        # clarification without advancing. Trip on a cheap,
                        # hard-to-game no-progress streak and hard-stop. The
                        # terminal notify in `finally` is the cheap ping; we do
                        # NOT route a stuck Worker through a fresh Marlin-Proxy
                        # turn it could influence (re-deciding per iteration
                        # would amplify rate-limit and spend).
                        # A `stop` is a terminal decision that TRIGGERS the
                        # verify + held-out gates (the real arbiters of a green),
                        # so the stagnation brake must never pre-empt it: doing so
                        # would let a slow-to-stop Proxy starve the gate and report
                        # stagnation on already-finished work. Stagnation only
                        # brakes a loop that keeps continuing (reply / escalate)
                        # without structured progress.
                        streak = update_stagnation(state)
                        if decision.action != "stop" and stagnation_hit(streak, cfg.stagnation_streak_cap):
                            state.status = "stopped"
                            state.exit_reason = (
                                f"stagnation: no structured progress for {streak} "
                                f"consecutive iterations (cap {cfg.stagnation_streak_cap})"
                            )
                            save_state(state_path, state)
                            local_console.print(f"[bold red]{state.exit_reason}[/bold red]")
                            return

                        # Proactive handover check: override a "reply" decision
                        # when context crosses the handover threshold, before
                        # quality degrades further.
                        if (
                            decision.action == "reply"
                            and mp_config.context_handover_tokens > 0
                            and state.usage
                            and state.usage[-1].input_tokens >= mp_config.context_handover_tokens
                        ):
                            tokens_now = state.usage[-1].input_tokens
                            local_console.print(
                                f"[bold yellow]handover:[/bold yellow] context threshold "
                                f"({tokens_now:,} >= {mp_config.context_handover_tokens:,} tokens), "
                                f"overriding reply with handover"
                            )
                            decision = ProxyDecision(
                                action="handover",
                                text=build_handover_prompt(state),
                                reasoning=f"context threshold ({tokens_now:,} tokens)",
                            )

                        save_state(state_path, state)

                        if decision.action == "stop":
                            # No gate at all: neither an in-tree verify command
                            # nor a held-out command for this repo. Complete with
                            # a logged warning (no build verification).
                            if verify_config.command is None and not state.held_out_verify:
                                state.status = "completed"
                                state.exit_reason = (
                                    decision.reasoning or "proxy stopped (no verify gate)"
                                )
                                save_state(state_path, state)
                                local_console.print(
                                    "[yellow]completed WITHOUT verify gate "
                                    "(no `verify` command and no held-out verifier)[/yellow]"
                                )
                                return

                            # In-tree verify gate: the goal's own command. A
                            # failure feeds the Worker (evaluator-optimizer) up to
                            # fix_cap then escalates; a pass falls through to the
                            # tamper tripwire and then the held-out gate.
                            if verify_config.command is not None:
                                local_console.print(
                                    "[bold]verify:[/bold] running gate before accepting completion"
                                )
                                outcome = await run_verify(
                                    verify_config.command,
                                    work_dir,
                                    verify_config.timeout_s,
                                )
                                state.last_verify = VerifyRecord(
                                    iteration=state.iteration,
                                    command=outcome.command,
                                    status=outcome.status,
                                    exit_code=outcome.exit_code,
                                    tail=outcome.tail,
                                )
                                gate = decide_after_verify(
                                    outcome=outcome,
                                    prior_attempts=state.verify_attempts,
                                    fix_cap=verify_config.fix_cap,
                                )
                                state.verify_attempts = gate.attempts

                                if gate.action == "escalate":
                                    state.status = "escalated"
                                    state.exit_reason = gate.exit_reason
                                    save_state(state_path, state)
                                    local_console.print(
                                        f"[bold red]verify: ESCALATE[/bold red] {gate.exit_reason}"
                                    )
                                    return

                                if gate.action == "retry":
                                    # evaluator-optimizer: feed the failure back to
                                    # the Worker; the Proxy re-decides next turn.
                                    save_state(state_path, state)
                                    local_console.print(
                                        f"[yellow]verify: FAIL[/yellow] attempt "
                                        f"{state.verify_attempts}/{verify_config.fix_cap}; "
                                        "feeding failure back to the Worker"
                                    )
                                    next_message = gate.next_message
                                    continue

                                # gate.action == "complete": cheap tamper tripwire
                                # before we trust the green. A deleted test or a
                                # dropped assertion count downgrades to escalate
                                # (path-touched alone is a log signal only).
                                tamper = scan_tamper(
                                    work_dir,
                                    state.baseline_ref,
                                    [f.path for f in state.files_touched],
                                )
                                if tamper.log_paths:
                                    local_console.print(
                                        f"[dim]tamper: {len(tamper.log_paths)} test file(s) "
                                        f"edited (log only): {', '.join(tamper.log_paths)}[/dim]"
                                    )
                                if tamper.tripped:
                                    state.tamper_paths = tamper.strong_paths
                                    state.status = "escalated"
                                    state.exit_reason = (
                                        "verify passed but tamper tripwire fired "
                                        "(possible reward hack): " + "; ".join(tamper.details)
                                    )
                                    save_state(state_path, state)
                                    local_console.print(
                                        f"[bold red]verify PASS but TAMPER:[/bold red] "
                                        f"{state.exit_reason}"
                                    )
                                    return
                                local_console.print("[bold green]verify: PASS[/bold green]")

                            # Held-out gate (trust boundary): an operator-sourced
                            # test set on a path the Worker cannot write, resolved
                            # from the repo registry. Runs after the in-tree verify
                            # passed (or as the sole gate when there is none). A
                            # FAIL is the reward-hack fingerprint (visible green,
                            # hidden red) and escalates, never a Worker retry.
                            if state.held_out_verify:
                                local_console.print(
                                    "[bold]held-out:[/bold] running the operator's "
                                    "out-of-reach test set"
                                )
                                ho_outcome = await run_verify(
                                    state.held_out_verify,
                                    work_dir,
                                    verify_config.timeout_s,
                                )
                                state.last_held_out = HeldOutRecord(
                                    iteration=state.iteration,
                                    command=ho_outcome.command,
                                    status=ho_outcome.status,
                                    exit_code=ho_outcome.exit_code,
                                    tail=ho_outcome.tail,
                                )
                                ho = decide_after_held_out(
                                    ho_outcome,
                                    intree_verified=verify_config.command is not None,
                                )
                                if ho.action == "escalate":
                                    state.status = "escalated"
                                    state.exit_reason = ho.exit_reason
                                    save_state(state_path, state)
                                    local_console.print(
                                        f"[bold red]held-out: ESCALATE[/bold red] {ho.exit_reason}"
                                    )
                                    return
                                local_console.print(
                                    "[bold green]held-out: PASS[/bold green] "
                                    "(green corroborated by out-of-reach tests)"
                                )

                            state.status = "completed"
                            state.exit_reason = (
                                decision.reasoning or "proxy stopped; verify passed"
                            )
                            save_state(state_path, state)
                            local_console.print("[bold green]completed[/bold green]")
                            return

                        if decision.action == "handover":
                            seed = await _execute_handover(
                                client=client,
                                handover_prompt=decision.text,
                                state=state,
                                state_path=state_path,
                                cfg=cfg,
                                work_dir=work_dir,
                                persona=persona,
                                mp_config=mp_config,
                                local_console=local_console,
                            )
                            if seed is None:
                                # Worker failed to produce HANDOVER.md; already escalated.
                                return
                            raise _HandoverSignal(seed)

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
            except _HandoverSignal as hs:
                next_message = hs.seed
                leg += 1
                transient_retries = 0
                leg_count = len(state.handovers)
                local_console.print(
                    f"[bold yellow]handover:[/bold yellow] starting fresh leg {leg_count + 1}"
                )
                continue
            except Exception as e:
                # Transient upstream blip (529 Overloaded, rate-limit, dropped
                # connection): back off and retry the SAME leg instead of failing
                # the whole run. A real error (bad config, auth, a bug) still
                # fails fast. Without this, any multi-hour run during an Anthropic
                # load event dies and needs a manual relaunch. Transient retries
                # do not consume a handover leg.
                if is_transient_sdk_error(e) and transient_retries < MAX_TRANSIENT_RETRIES:
                    transient_retries += 1
                    state = load_state(state_path)
                    state.transient_retries += 1
                    save_state(state_path, state)
                    delay = backoff_delay(transient_retries)
                    local_console.print(
                        f"[yellow]transient SDK error "
                        f"(retry {transient_retries}/{MAX_TRANSIENT_RETRIES} "
                        f"after {delay:.0f}s): {type(e).__name__}: {e}[/yellow]"
                    )
                    await asyncio.sleep(delay)
                    continue
                state = load_state(state_path)
                state.status = "failed"
                state.exit_reason = f"sdk error: {type(e).__name__}: {e}"
                save_state(state_path, state)
                local_console.print(f"[bold red]SDK ERROR:[/bold red] {e}")
                raise
            # Normal exit (stop, escalate, deferred) - do not start another leg.
            break
    finally:
        # Worktree teardown (never loses work): committed work lives on the
        # attempt branch and survives removal; `git worktree remove` refuses on a
        # dirty/untracked tree and we never --force. A run that needs human eyes
        # (escalated/failed) keeps its worktree so the live tree is inspectable.
        if worktree_active and worktree_path is not None:
            try:
                branch = worktree_branch(cfg.task_id)
                if state.status in ("escalated", "failed"):
                    local_console.print(
                        f"[yellow]worktree retained for inspection: {worktree_path} "
                        f"(status={state.status}); work is on branch {branch}[/yellow]"
                    )
                else:
                    removed, msg = remove_worktree(cfg.project_dir, worktree_path)
                    if removed:
                        local_console.print(
                            f"[dim]worktree removed; work preserved on branch {branch}[/dim]"
                        )
                    else:
                        local_console.print(
                            f"[yellow]worktree retained at {worktree_path} "
                            f"(not clean: {msg}); reconcile manually, never force-remove[/yellow]"
                        )
            except Exception:
                pass

        # Ping on terminal state so detached runs do not finish silently. This is
        # the human-facing notify (macOS banner + optional webhook); the
        # complementary "wake the dispatching session" path is the harness-tracked
        # launch documented in the skill. Best-effort: never break the run.
        try:
            if state.status in TERMINAL_STATUSES:
                notify(
                    task_id=cfg.task_id,
                    status=state.status,
                    reason=state.exit_reason or "",
                )
        except Exception:
            pass
        if log_file is not None:
            try:
                log_file.flush()
                log_file.close()
            except Exception:
                pass
