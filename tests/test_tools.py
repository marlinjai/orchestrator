from pathlib import Path

import pytest

from orchestrator.state import PlanStep, State, load_state, save_state
from orchestrator.tools import build_update_state_handler


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    p = tmp_path / "state.json"
    save_state(p, State(task_id="t1", goal="g"))
    return p


async def test_update_state_appends_decision(state_path: Path):
    handler = build_update_state_handler(state_path)
    result = await handler(
        {
            "kind": "decision",
            "turn": 3,
            "question": "scope right?",
            "answer": "yes",
            "reasoning": "checked",
            "decided_by": "proxy",
        }
    )
    assert result["content"][0]["text"].startswith("ok")
    state = load_state(state_path)
    assert len(state.decisions) == 1
    assert state.decisions[0].question == "scope right?"


async def test_update_state_appends_files_touched(state_path: Path):
    handler = build_update_state_handler(state_path)
    await handler({"kind": "file_touched", "path": "src/foo.py"})
    state = load_state(state_path)
    assert state.files_touched == ["src/foo.py"]


async def test_update_state_appends_commit(state_path: Path):
    handler = build_update_state_handler(state_path)
    await handler({"kind": "commit", "sha": "deadbee"})
    state = load_state(state_path)
    assert state.commits == ["deadbee"]


async def test_update_state_advances_step(state_path: Path):
    state = load_state(state_path)
    state.plan = [
        PlanStep(id=1, step="a", status="pending"),
        PlanStep(id=2, step="b", status="pending"),
    ]
    save_state(state_path, state)

    handler = build_update_state_handler(state_path)
    await handler({"kind": "step_completed", "step_id": 1})
    state = load_state(state_path)
    assert state.plan[0].status == "completed"


async def test_update_state_unknown_kind_returns_error(state_path: Path):
    handler = build_update_state_handler(state_path)
    result = await handler({"kind": "nonsense"})
    assert "error" in result["content"][0]["text"].lower()


async def test_update_state_decision_missing_field_returns_error(state_path: Path):
    handler = build_update_state_handler(state_path)
    result = await handler({"kind": "decision", "turn": 1})
    assert "error" in result["content"][0]["text"].lower()


async def test_update_state_step_completed_unknown_id_warns(state_path: Path):
    handler = build_update_state_handler(state_path)
    result = await handler({"kind": "step_completed", "step_id": 99})
    assert "warning" in result["content"][0]["text"].lower()
