from orchestrator.state import (
    CommitEntry,
    Decision,
    FileTouched,
    PlanStep,
    State,
    VerifyRecord,
)
from orchestrator.stagnation import (
    DEFAULT_STAGNATION_STREAK_CAP,
    progress_key,
    stagnation_hit,
    update_stagnation,
)


def _state(**kw) -> State:
    return State(task_id="t", goal="g", **kw)


def test_progress_key_stable_for_identical_state():
    s = _state(current_step_id=2)
    assert progress_key(s) == progress_key(s)


def test_noop_commit_does_not_change_key():
    # The dominant gaming move: commit junk each iteration to dodge detection.
    s = _state(current_step_id=1)
    before = progress_key(s)
    s.commits.append(CommitEntry(sha="abc123", message="noop"))
    s.files_touched.append(FileTouched(path="junk.txt"))
    assert progress_key(s) == before


def test_advancing_step_changes_key():
    s = _state(current_step_id=1)
    before = progress_key(s)
    s.current_step_id = 2
    assert progress_key(s) != before


def test_completing_a_plan_step_changes_key():
    s = _state(plan=[PlanStep(id=1, step="a"), PlanStep(id=2, step="b")])
    before = progress_key(s)
    s.plan[0].status = "completed"
    assert progress_key(s) != before


def test_recording_a_decision_changes_key():
    s = _state()
    before = progress_key(s)
    s.decisions.append(
        Decision(turn=1, question="q", answer="a", reasoning="r", decided_by="proxy")
    )
    assert progress_key(s) != before


def test_verify_outcome_change_changes_key():
    s = _state()
    s.last_verify = VerifyRecord(
        iteration=1, command="t", status="fail", exit_code=1, tail="err A"
    )
    before = progress_key(s)
    s.last_verify = VerifyRecord(
        iteration=2, command="t", status="fail", exit_code=2, tail="err B"
    )
    assert progress_key(s) != before


def test_update_stagnation_increments_then_resets():
    s = _state(current_step_id=1)
    assert update_stagnation(s) == 0  # first observation only sets the baseline
    assert update_stagnation(s) == 1  # unchanged -> streak grows
    assert update_stagnation(s) == 2
    s.current_step_id = 2  # real progress
    assert update_stagnation(s) == 0


def test_noop_commit_does_not_reset_streak():
    s = _state(current_step_id=1)
    update_stagnation(s)  # baseline -> 0
    update_stagnation(s)  # -> 1
    s.commits.append(CommitEntry(sha="deadbeef", message="noop"))
    # churn is not progress: the streak keeps climbing
    assert update_stagnation(s) == 2


def test_stagnation_hit_threshold():
    assert not stagnation_hit(0, 3)
    assert not stagnation_hit(2, 3)
    assert stagnation_hit(3, 3)
    assert stagnation_hit(4, 3)


def test_stagnation_hit_disabled_when_cap_nonpositive():
    assert not stagnation_hit(100, 0)
    assert not stagnation_hit(100, -1)


def test_default_cap_is_conservative():
    assert DEFAULT_STAGNATION_STREAK_CAP >= 2
