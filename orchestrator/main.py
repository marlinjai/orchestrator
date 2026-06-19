import asyncio
import os
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from orchestrator.config import load_config
from orchestrator.guardrails import cumulative_tokens
from orchestrator.ledger import agreement_by_category, read_entries
from orchestrator.orchestrator import OrchestratorConfig, run_orchestrator
from orchestrator.state import load_state
from orchestrator.usage_guard import global_kill_active, tokens_in_window


app = typer.Typer(help="Autonomous Claude Code orchestrator")
marlin_app = typer.Typer(help="Marlin Proxy: review and manage layered-autonomy decisions")
app.add_typer(marlin_app, name="marlin-proxy")
console = Console()


def _home() -> Path:
    return Path(os.environ.get("ORCHESTRATOR_HOME", str(Path.home() / ".orchestrator")))


def _task_dir(task_id: str) -> Path:
    return _home() / "tasks" / task_id


def _daily_token_cap() -> int | None:
    """Fleet-wide rolling 24h token budget from ORCHESTRATOR_DAILY_TOKEN_CAP.

    Operator-owned and un-promptable (env, not goal frontmatter), so no task can
    relax it. Returns None (off) when unset, zero, or malformed.
    """
    raw = os.environ.get("ORCHESTRATOR_DAILY_TOKEN_CAP")
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


@app.command()
def start(
    goal: Path = typer.Option(..., "--goal", help="Path to goal markdown file"),
    persona: Path = typer.Option(
        Path(__file__).parent.parent / "personas" / "default.md",
        "--persona",
        help="Path to persona markdown file",
    ),
    project: Path = typer.Option(Path.cwd(), "--project", help="Project working directory"),
    task_id: str = typer.Option("", "--task-id", help="Task ID (auto-generated if empty)"),
    max_iterations: int = typer.Option(50, "--max-iterations"),
    max_hours: float = typer.Option(4.0, "--max-hours"),
    auth_mode: str = typer.Option(
        "subscription",
        "--auth-mode",
        help=(
            "Anthropic auth for the Worker: 'subscription' (scrub the API key, "
            "use the Claude login) or 'api_key' (keep ANTHROPIC_API_KEY, bill the "
            "metered API). From 2026-06-15 headless subscription use is metered."
        ),
    ),
    max_cost_usd: float = typer.Option(
        0.0,
        "--max-cost-usd",
        help=(
            "Hard USD ceiling; the run stops when the estimated metered cost "
            "crosses it. 0 = default (api_key mode auto-caps at "
            "$20; subscription is uncapped)."
        ),
    ),
    max_tokens: int = typer.Option(
        0,
        "--max-tokens",
        help=(
            "Per-run cumulative token ceiling (rate-limit runaway guard, counts "
            "input + output + cache). The run stops when crossed. 0 = off. The "
            "fleet-wide daily ceiling is set with the ORCHESTRATOR_DAILY_TOKEN_CAP "
            "env var (un-promptable, applies across all runs)."
        ),
    ),
    marlin_persona: Path = typer.Option(
        Path(__file__).parent.parent / "personas" / "marlin.md",
        "--marlin-persona",
        help="Path to the Marlin Proxy persona (used when marlin_proxy mode != off)",
    ),
    worktree: bool = typer.Option(
        False,
        "--worktree",
        help=(
            "Run the Worker in its own git worktree (isolated attempt branch "
            "orchestrator/<task-id>) instead of editing --project in place. "
            "Commits land on the branch; a clean worktree is auto-removed at the "
            "end, an escalated/failed one is retained for inspection. Requires a "
            "git repo; non-git falls back to in-place."
        ),
    ),
):
    """Start a new autonomous task."""
    if auth_mode not in ("subscription", "api_key"):
        console.print(
            f"[red]invalid --auth-mode {auth_mode!r}; use 'subscription' or 'api_key'[/red]"
        )
        raise typer.Exit(1)
    tid = task_id or uuid.uuid4().hex[:8]
    state_dir = _task_dir(tid)
    cfg = OrchestratorConfig(
        task_id=tid,
        goal_file=goal,
        persona_file=persona,
        project_dir=project,
        state_dir=state_dir,
        max_iterations=max_iterations,
        max_seconds=max_hours * 3600,
        log_path=state_dir / "run.log",
        marlin_persona_file=marlin_persona,
        auth_mode=auth_mode,  # type: ignore[arg-type]
        max_cost_usd=(max_cost_usd if max_cost_usd > 0 else None),
        max_tokens=(max_tokens if max_tokens > 0 else None),
        daily_token_cap=_daily_token_cap(),
        orchestrator_home=_home(),
        worktree_isolation=worktree,
    )
    console.print(f"[bold green]starting task {tid}[/bold green]")
    console.print(f"  goal: {goal}")
    console.print(f"  project: {project}")
    console.print(f"  state: {cfg.state_dir}")
    asyncio.run(run_orchestrator(cfg))


@app.command()
def stop(task_id: str = typer.Option(..., "--task-id")):
    """Trigger the kill switch for a running task."""
    td = _task_dir(task_id)
    if not td.exists():
        console.print(f"[red]task {task_id} not found at {td}[/red]")
        raise typer.Exit(1)
    (td / "STOP").touch()
    console.print(f"[yellow]kill switch set: {td / 'STOP'}[/yellow]")


@app.command()
def status(task_id: str = typer.Option(..., "--task-id")):
    """Show current state.json for a task."""
    state_path = _task_dir(task_id) / "state.json"
    if not state_path.exists():
        console.print(f"[red]no state for task {task_id} at {state_path}[/red]")
        raise typer.Exit(1)
    state = load_state(state_path)
    table = Table(title=f"task {state.task_id}")
    table.add_column("field")
    table.add_column("value")
    table.add_row("status", state.status)
    table.add_row("iteration", f"{state.iteration} / {state.max_iterations}")
    table.add_row("goal", state.goal)
    proxy_files = sum(1 for f in state.files_touched if f.decided_by == "proxy")
    system_files = sum(1 for f in state.files_touched if f.decided_by == "system")
    proxy_commits = sum(1 for c in state.commits if c.decided_by == "proxy")
    system_commits = sum(1 for c in state.commits if c.decided_by == "system")
    table.add_row(
        "files_touched",
        f"{len(state.files_touched)} (proxy={proxy_files}, system={system_files})",
    )
    table.add_row(
        "commits",
        f"{len(state.commits)} (proxy={proxy_commits}, system={system_commits})",
    )
    table.add_row("decisions", str(len(state.decisions)))
    table.add_row("baseline_ref", (state.baseline_ref or "")[:12])
    table.add_row("repo_remote", state.repo_remote or "(no git remote)")
    if state.stakes_tier is not None:
        table.add_row("stakes_tier", str(state.stakes_tier))
    table.add_row(
        "held_out_verify",
        "configured" if state.held_out_verify else "not configured",
    )
    if state.last_held_out is not None:
        ho = state.last_held_out
        table.add_row(
            "held_out_result",
            f"{ho.status} (exit {ho.exit_code}) @ iter {ho.iteration}",
        )
    if state.usage:
        in_tok = sum(u.input_tokens for u in state.usage)
        out_tok = sum(u.output_tokens for u in state.usage)
        cache_r = sum(u.cache_read_tokens for u in state.usage)
        cache_c = sum(u.cache_creation_tokens for u in state.usage)
        worker_ms = sum(u.worker_ms for u in state.usage)
        proxy_ms = sum(u.proxy_ms for u in state.usage)
        table.add_row(
            "tokens",
            f"in={in_tok} out={out_tok} cache_r={cache_r} cache_c={cache_c}",
        )
        table.add_row(
            "usage_total",
            f"{cumulative_tokens(state.usage):,} tokens (rate-limit figure)",
        )
        table.add_row("wall_ms", f"worker={worker_ms} proxy={proxy_ms}")
        table.add_row("est_cost_usd", f"${state.estimated_cost_usd:.2f}")

    # Fleet-wide usage + kill state (shared across all runs on this home).
    home = _home()
    daily_cap = _daily_token_cap()
    today = tokens_in_window(home)
    cap_label = f"{daily_cap:,}" if daily_cap else "none"
    table.add_row("global_today", f"{today:,} tokens / cap {cap_label} (rolling 24h)")
    if global_kill_active(home):
        table.add_row("global_kill", "ACTIVE (fleet-wide STOP file present)")

    if state.tamper_paths:
        table.add_row("tamper_paths", ", ".join(state.tamper_paths))
    if state.assumptions_made:
        table.add_row("assumptions", str(len(state.assumptions_made)))
    if state.plan_contradictions:
        table.add_row("plan_contradictions", str(len(state.plan_contradictions)))
    if state.confidence is not None:
        table.add_row("confidence", f"{state.confidence:.2f} (logged only, not a gate)")
    a = state.autonomy_stats
    if a.auto_approved or a.auto_deferred or a.escalated:
        table.add_row(
            "marlin-proxy",
            f"approved={a.auto_approved} deferred={a.auto_deferred} escalated={a.escalated}",
        )
        table.add_row(
            "autonomy",
            f"max_streak={a.max_decisions_between_escalations} "
            f"runtime_ms={a.autonomous_runtime_ms}",
        )
    table.add_row("exit_reason", state.exit_reason or "")
    console.print(table)


@marlin_app.command("review")
def marlin_review():
    """Review Marlin Proxy decisions: agreement rate by category, disagreements."""
    cfg = load_config()
    entries = read_entries(cfg.ledger_path)
    if not entries:
        console.print(f"[yellow]no marlin-proxy decisions yet at {cfg.ledger_path}[/yellow]")
        return

    agg = agreement_by_category(entries)
    table = Table(title=f"Marlin Proxy review ({len(entries)} decisions)")
    table.add_column("category")
    table.add_column("total", justify="right")
    table.add_column("judged", justify="right")
    table.add_column("agreed", justify="right")
    table.add_column("rate", justify="right")
    for cat in sorted(agg):
        c = agg[cat]
        rate = "n/a" if c.agreement_rate is None else f"{c.agreement_rate * 100:.0f}%"
        table.add_row(cat, str(c.total), str(c.judged), str(c.agreed), rate)
    console.print(table)

    disagreements = [e for e in entries if e.agreed is False]
    if disagreements:
        console.print(f"\n[bold red]{len(disagreements)} disagreements:[/bold red]")
        for e in disagreements[-10:]:
            console.print(
                f"  [{e.category}] proxy={e.proxy_choice} actual={e.actual_choice} "
                f": {e.proxy_reason}"
            )


@app.command()
def logs(
    task_id: str = typer.Option(..., "--task-id"),
    follow: bool = typer.Option(False, "--follow", "-f"),
):
    """Tail the orchestrator log for a task."""
    log_path = _task_dir(task_id) / "run.log"
    if not log_path.exists():
        console.print(f"[red]no log for task {task_id}[/red]")
        raise typer.Exit(1)
    if follow:
        os.execvp("tail", ["tail", "-f", str(log_path)])
    else:
        console.print(log_path.read_text())


@app.command("roadmap-next")
def roadmap_next(
    root: list[str] = typer.Option(..., "--root", help="plan-doc root to scan (repeatable)"),
    goals_dir: str = typer.Option("goals", "--goals-dir", help="where to write the goal file"),
    index: int = typer.Option(0, "--index", "-i", help="queue position to scaffold (0 = top)"),
    include_in_progress: bool = typer.Option(False, "--include-in-progress"),
):
    """Scaffold a goal file from the top of the closed-loop-sync roadmap queue.

    Picks the work item and writes a goal stub referencing the source plan.
    The target repo (--project) is intentionally left for you to assign before
    dispatch: a roadmap plan does not encode which repo implements it.
    """
    from orchestrator.roadmap import RoadmapError, next_goal

    try:
        result = next_goal(root, goals_dir, index=index,
                           include_in_progress=include_in_progress)
    except RoadmapError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    item = result["item"]
    console.print(f"[green]Scaffolded goal[/green] [bold]{result['task_id']}[/bold] "
                  f"(item {index + 1} of {result['total']})")
    console.print(f"  plan:  {item.get('path')}")
    console.print(f"  goal:  {result['goal_path']}")
    console.print("[yellow]Next:[/yellow] set --project + verify in the goal, "
                  "create a worktree, then `orchestrator start`.")


if __name__ == "__main__":
    app()
