import json
from pathlib import Path
import pytest
from orchestrator.state import (
    CommitEntry,
    Decision,
    FileTouched,
    IterationUsage,
    PlanStep,
    State,
    ground_truth_summary,
    load_state,
    save_state,
)


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
    assert loaded.commits[0].sha == "efbdd5f"
    assert loaded.commits[0].decided_by == "proxy"
    assert loaded.files_touched[0].path == "orchestrator/state.py"
    assert loaded.usage[0].input_tokens == 1000
    assert loaded.baseline_ref == "abc1234567890"

    # Round-trip the started_at field through save + load to validate
    # pydantic's ISO 8601 "Z" suffix parsing.
    original_started_at = loaded.started_at
    roundtrip_path = tmp_path / "roundtrip.json"
    save_state(roundtrip_path, loaded)
    reloaded = load_state(roundtrip_path)
    assert reloaded.started_at == original_started_at


def test_state_legacy_string_commits_rejected(tmp_path: Path):
    """The v0.1 schema had commits as list[str]. v0.2 requires CommitEntry
    objects. Old state.json files should fail validation rather than silently
    losing data. Per the dev-phase no-backcompat rule documented in CLAUDE.md."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"task_id": "x", "goal": "g", "commits": ["abc123"]})
    )
    with pytest.raises(ValueError):
        load_state(path)


def test_iteration_usage_defaults():
    u = IterationUsage(iteration=3)
    assert u.iteration == 3
    assert u.input_tokens == 0
    assert u.worker_ms == 0
    assert u.model == ""


def test_commit_entry_and_file_touched_defaults():
    c = CommitEntry(sha="deadbeef")
    assert c.decided_by == "proxy"
    assert c.message == ""
    f = FileTouched(path="a/b.py")
    assert f.decided_by == "proxy"


def test_state_new_logged_fields_default_empty():
    s = State(task_id="t", goal="g")
    assert s.tamper_paths == []
    assert s.assumptions_made == []
    assert s.plan_contradictions == []
    assert s.confidence is None


def test_ground_truth_summary_reports_no_tamper_by_default():
    s = State(task_id="t", goal="g")
    summary = ground_truth_summary(s)
    assert "tamper tripwire: 0 test file(s) weakened vs baseline (none)" in summary


def test_ground_truth_summary_surfaces_tamper_paths():
    s = State(task_id="t", goal="g", tamper_paths=["tests/test_a.py", "tests/test_b.py"])
    summary = ground_truth_summary(s)
    assert "tamper tripwire: 2 test file(s) weakened" in summary
    assert "tests/test_a.py" in summary
    assert "tests/test_b.py" in summary
