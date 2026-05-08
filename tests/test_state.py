import json
from pathlib import Path
import pytest
from orchestrator.state import State, PlanStep, Decision, load_state, save_state


def test_state_minimal_construction():
    s = State(task_id="abc", goal="do a thing")
    assert s.task_id == "abc"
    assert s.goal == "do a thing"
    assert s.iteration == 0
    assert s.status == "running"
    assert s.plan == []


def test_state_roundtrip(tmp_path: Path):
    s = State(
        task_id="abc",
        goal="do a thing",
        plan=[PlanStep(id=1, step="explore", status="completed")],
        decisions=[Decision(turn=1, question="ok?", answer="yes", reasoning="r", decided_by="proxy")],
    )
    path = tmp_path / "state.json"
    save_state(path, s)
    loaded = load_state(path)
    assert loaded == s


def test_save_state_atomic(tmp_path: Path):
    path = tmp_path / "state.json"
    s = State(task_id="abc", goal="g")
    save_state(path, s)
    assert path.exists()
    assert not (path.with_suffix(".json.tmp")).exists()


def test_load_state_rejects_corrupt(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("{not valid json")
    with pytest.raises(ValueError):
        load_state(path)


def test_load_state_rejects_schema_mismatch(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"unexpected": "shape"}))
    with pytest.raises(ValueError):
        load_state(path)
