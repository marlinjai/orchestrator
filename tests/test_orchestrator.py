from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.orchestrator import OrchestratorConfig, run_orchestrator
from orchestrator.proxy import ProxyDecision
from orchestrator.state import IterationUsage, load_state


def _turn(text: str, action: str, iteration: int = 1, reasoning: str = "r", text_out: str = "go"):
    """Build the (chunks, decision, usage) 3-tuple _run_one_turn now returns."""
    return (
        [text],
        ProxyDecision(action=action, text=text_out, reasoning=reasoning),
        IterationUsage(iteration=iteration),
    )


@pytest.fixture
def task_dir(tmp_path: Path) -> Path:
    (tmp_path / "goals").mkdir()
    (tmp_path / "personas").mkdir()
    (tmp_path / "goals" / "g.md").write_text("test goal")
    (tmp_path / "personas" / "p.md").write_text("test persona")
    return tmp_path


@pytest.fixture
def cfg(task_dir: Path) -> OrchestratorConfig:
    return OrchestratorConfig(
        task_id="test-task",
        goal_file=task_dir / "goals" / "g.md",
        persona_file=task_dir / "personas" / "p.md",
        project_dir=task_dir,
        state_dir=task_dir / ".orchestrator" / "test-task",
        max_iterations=3,
        max_seconds=60,
    )


async def test_orchestrator_writes_initial_state(cfg: OrchestratorConfig):
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        mock_turn.side_effect = [_turn("worker said done", "stop", text_out="", reasoning="done")]
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.task_id == "test-task"
    assert state.goal == "test goal"
    assert state.status == "completed"


async def test_orchestrator_iterates_until_proxy_stops(cfg: OrchestratorConfig):
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        mock_turn.side_effect = [
            _turn("t1", "reply", iteration=1, text_out="continue"),
            _turn("t2", "reply", iteration=2, text_out="continue"),
            _turn("t3", "stop", iteration=3, text_out="", reasoning="done"),
        ]
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.iteration == 3
    assert state.status == "completed"
    assert len(state.usage) == 3


async def test_orchestrator_halts_on_iteration_cap(cfg: OrchestratorConfig):
    cfg.max_iterations = 2
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        mock_turn.side_effect = [
            _turn("t1", "reply", iteration=1),
            _turn("t2", "reply", iteration=2),
        ]
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "stopped"
    assert "iteration" in (state.exit_reason or "").lower()


async def test_orchestrator_halts_on_kill_switch(cfg: OrchestratorConfig):
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "STOP").touch()
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "stopped"
    assert "kill" in (state.exit_reason or "").lower()
    mock_turn.assert_not_called()


async def test_orchestrator_halts_on_escalate(cfg: OrchestratorConfig):
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        mock_turn.side_effect = [_turn("t1", "escalate", text_out="need human", reasoning="money")]
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "escalated"


async def test_orchestrator_writes_to_log_file(task_dir: Path):
    """When log_path is set, orchestrator output is captured to that file."""
    log_path = task_dir / "run.log"
    cfg = OrchestratorConfig(
        task_id="log-test",
        goal_file=task_dir / "goals" / "g.md",
        persona_file=task_dir / "personas" / "p.md",
        project_dir=task_dir,
        state_dir=task_dir / ".orchestrator" / "log-test",
        max_iterations=2,
        max_seconds=60,
        log_path=log_path,
    )
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        mock_turn.side_effect = [_turn("worker output", "stop", text_out="", reasoning="done")]
        await run_orchestrator(cfg)
    assert log_path.exists()
    contents = log_path.read_text()
    assert contents.strip(), "expected log file to contain orchestrator output"
    assert "iteration 1" in contents.lower()


async def test_orchestrator_marks_failed_on_sdk_error(cfg: OrchestratorConfig):
    class FakeError(RuntimeError):
        pass

    with patch("orchestrator.orchestrator.ClaudeSDKClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.side_effect = FakeError("auth blew up")
        with pytest.raises(FakeError):
            await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "failed"
    assert "auth blew up" in (state.exit_reason or "")
