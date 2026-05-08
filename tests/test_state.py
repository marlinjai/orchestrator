import json
from pathlib import Path
import pytest
from orchestrator.state import State, PlanStep, Decision, load_state, save_state


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "state_sample.json"


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
    assert list(tmp_path.glob(f"{path.name}.*.tmp")) == []


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


def test_save_state_cleans_tempfile_on_exception(tmp_path: Path, monkeypatch):
    path = tmp_path / "state.json"
    original_content = '{"existing": "data"}'
    path.write_text(original_content)

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("orchestrator.state.os.replace", boom)

    s = State(task_id="abc", goal="g")
    with pytest.raises(OSError):
        save_state(path, s)

    assert path.read_text() == original_content
    assert list(tmp_path.glob(f"{path.name}.*.tmp")) == []


def test_load_state_from_fixture(tmp_path: Path):
    loaded = load_state(FIXTURE_PATH)
    assert loaded.task_id == "sample-001"
    assert loaded.goal == "example task for fixture"
    assert loaded.iteration == 2
    assert loaded.current_step_id == 2
    assert len(loaded.plan) == 2
    assert loaded.plan[0].status == "completed"
    assert loaded.handovers[0].doc == "handover_001.md"

    # Round-trip the started_at field through save + load to validate
    # pydantic's ISO 8601 "Z" suffix parsing.
    original_started_at = loaded.started_at
    roundtrip_path = tmp_path / "roundtrip.json"
    save_state(roundtrip_path, loaded)
    reloaded = load_state(roundtrip_path)
    assert reloaded.started_at == original_started_at
