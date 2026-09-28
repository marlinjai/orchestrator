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


# ---- update_state: late reports upgrade reconciled entries (the Mercury tail) ----


async def _call(state_path, **args):
    from orchestrator.tools import build_update_state_handler

    res = await build_update_state_handler(state_path)(args)
    return res["content"][0]["text"]


def _state_with(tmp_path, **fields):
    from orchestrator.state import State, save_state

    p = tmp_path / "state.json"
    save_state(p, State(task_id="t", goal="g", **fields))
    return p


async def test_late_commit_report_upgrades_the_reconciled_entry(tmp_path):
    from orchestrator.state import CommitEntry, load_state

    full = "5cbc341288bb2c5d495024dee9c8b37404432a2f"
    p = _state_with(tmp_path, commits=[CommitEntry(sha=full, message="fix", decided_by="system")])
    out = await _call(p, kind="commit", sha="5cbc341", message="fix")
    assert "now marked as self-reported" in out
    (entry,) = load_state(p).commits
    assert entry.decided_by == "proxy" and entry.sha == full


async def test_repeated_commit_report_is_not_duplicated(tmp_path):
    from orchestrator.state import load_state

    p = _state_with(tmp_path)
    await _call(p, kind="commit", sha="a" * 40)
    out = await _call(p, kind="commit", sha="a" * 7)
    assert "already recorded" in out
    assert len(load_state(p).commits) == 1


@pytest.mark.parametrize("sha", ["", "abc", "not-a-sha-at-all"])
async def test_commit_without_a_real_sha_is_refused_with_guidance(tmp_path, sha):
    from orchestrator.state import load_state

    p = _state_with(tmp_path)
    out = await _call(p, kind="commit", sha=sha)
    assert out.startswith("error:") and "git rev-parse HEAD" in out
    assert load_state(p).commits == []


async def test_reporting_the_baseline_commit_is_refused(tmp_path):
    base = "b" * 40
    p = _state_with(tmp_path, baseline_ref=base)
    out = await _call(p, kind="commit", sha=base[:7])
    assert out.startswith("error:") and "starting commit" in out


async def test_late_file_report_upgrades_and_does_not_duplicate(tmp_path):
    from orchestrator.state import FileTouched, load_state

    p = _state_with(tmp_path, files_touched=[FileTouched(path="a.py", decided_by="system")])
    assert "now marked as self-reported" in await _call(p, kind="file_touched", path="a.py")
    assert "already recorded" in await _call(p, kind="file_touched", path="a.py")
    (entry,) = load_state(p).files_touched
    assert entry.decided_by == "proxy"
