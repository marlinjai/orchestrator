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
    assert len(state.files_touched) == 1
    assert state.files_touched[0].path == "src/foo.py"
    assert state.files_touched[0].decided_by == "proxy"


async def test_update_state_appends_commit(state_path: Path):
    handler = build_update_state_handler(state_path)
    await handler({"kind": "commit", "sha": "deadbee", "message": "feat: x"})
    state = load_state(state_path)
    assert len(state.commits) == 1
    assert state.commits[0].sha == "deadbee"
    assert state.commits[0].message == "feat: x"
    assert state.commits[0].decided_by == "proxy"


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


async def test_update_state_records_assumption(state_path: Path):
    handler = build_update_state_handler(state_path)
    await handler({"kind": "assumption", "assumption": "the API returns ISO dates"})
    state = load_state(state_path)
    assert state.assumptions_made == ["the API returns ISO dates"]


async def test_update_state_records_plan_contradiction(state_path: Path):
    handler = build_update_state_handler(state_path)
    await handler(
        {"kind": "plan_contradiction", "contradiction": "goal says SQLite, repo uses Postgres"}
    )
    state = load_state(state_path)
    assert state.plan_contradictions == ["goal says SQLite, repo uses Postgres"]


async def test_update_state_records_confidence(state_path: Path):
    handler = build_update_state_handler(state_path)
    await handler({"kind": "confidence", "confidence": 0.7})
    state = load_state(state_path)
    assert state.confidence == 0.7


async def test_update_state_confidence_bad_value_errors(state_path: Path):
    handler = build_update_state_handler(state_path)
    result = await handler({"kind": "confidence", "confidence": "high"})
    assert "error" in result["content"][0]["text"].lower()
    # state must be untouched on a bad write
    assert load_state(state_path).confidence is None


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
