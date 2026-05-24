import asyncio
import os
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from orchestrator.orchestrator import OrchestratorConfig, run_orchestrator
from orchestrator.state import load_state


app = typer.Typer(help="Autonomous Claude Code orchestrator")
console = Console()


def _home() -> Path:
    return Path(os.environ.get("ORCHESTRATOR_HOME", str(Path.home() / ".orchestrator")))


def _task_dir(task_id: str) -> Path:
    return _home() / "tasks" / task_id


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
):
    """Start a new autonomous task."""
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
        table.add_row("wall_ms", f"worker={worker_ms} proxy={proxy_ms}")
    table.add_row("exit_reason", state.exit_reason or "")
    console.print(table)


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


if __name__ == "__main__":
    app()
