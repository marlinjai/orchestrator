import time
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient
from rich.console import Console

from orchestrator.guardrails import (
    iteration_cap_hit,
    kill_switch_active,
    wall_clock_cap_hit,
)
from orchestrator.proxy import ProxyDecision, run_proxy_decision
from orchestrator.state import State, load_state, save_state
from orchestrator.transcript import AssistantTurn
from orchestrator.worker import build_worker_options, run_worker_turn


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


console = Console()


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
) -> tuple[list[str], ProxyDecision]:
    chunks: list[str] = []
    async for msg in run_worker_turn(client=client, user_message=user_message):
        text = _extract_text(msg)
        if text:
            chunks.append(text)
            console.print(f"[dim]worker:[/dim] {text}", end="")
    recent = [AssistantTurn(text=t) for t in chunks if t.strip()][-transcript_window:]
    decision = await run_proxy_decision(
        persona=persona,
        state=state,
        recent_turns=recent,
    )
    return chunks, decision


def _extract_text(msg) -> str:
    if isinstance(msg, dict):
        content = msg.get("message", {}).get("content")
        if isinstance(content, list):
            return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if hasattr(msg, "content"):
        c = msg.content
        if isinstance(c, list):
            return "".join(getattr(b, "text", "") for b in c)
    return ""


async def run_orchestrator(cfg: OrchestratorConfig) -> None:
    state = _initialize_state(cfg)
    state_path = cfg.state_dir / "state.json"
    persona = cfg.persona_file.read_text().strip()
    started_at = time.time()
    kill_switch = cfg.state_dir / "STOP"

    if kill_switch_active(kill_switch):
        state.status = "stopped"
        state.exit_reason = "kill switch active before start"
        save_state(state_path, state)
        console.print("[red]kill switch active. exiting.[/red]")
        return

    initial_message = state.goal
    options = build_worker_options(
        state_path=state_path,
        project_dir=cfg.project_dir,
        denied_bash=[],
    )

    async with ClaudeSDKClient(options=options) as client:
        next_message = initial_message
        while True:
            if iteration_cap_hit(iteration=state.iteration, max_iterations=cfg.max_iterations):
                state.status = "stopped"
                state.exit_reason = f"iteration cap reached ({cfg.max_iterations})"
                save_state(state_path, state)
                console.print(f"[yellow]{state.exit_reason}[/yellow]")
                return
            if wall_clock_cap_hit(started_at=started_at, max_seconds=cfg.max_seconds):
                state.status = "stopped"
                state.exit_reason = f"wall-clock cap reached ({cfg.max_seconds}s)"
                save_state(state_path, state)
                console.print(f"[yellow]{state.exit_reason}[/yellow]")
                return
            if kill_switch_active(kill_switch):
                state.status = "stopped"
                state.exit_reason = "kill switch activated"
                save_state(state_path, state)
                console.print("[red]kill switch activated. exiting.[/red]")
                return

            state.iteration += 1
            save_state(state_path, state)
            console.print(f"\n[bold cyan]=== iteration {state.iteration} ===[/bold cyan]")

            chunks, decision = await _run_one_turn(
                client=client,
                user_message=next_message,
                persona=persona,
                state=state,
                transcript_window=cfg.transcript_window,
            )
            console.print(f"\n[bold magenta]proxy:[/bold magenta] {decision.action} ({decision.reasoning})")

            state = load_state(state_path)
            if decision.action == "stop":
                state.status = "completed"
                state.exit_reason = decision.reasoning or "proxy stopped"
                save_state(state_path, state)
                return
            if decision.action == "escalate":
                state.status = "escalated"
                state.exit_reason = decision.text or decision.reasoning
                save_state(state_path, state)
                console.print(f"[bold red]ESCALATE:[/bold red] {decision.text}")
                return
            next_message = decision.text or "Continue."
