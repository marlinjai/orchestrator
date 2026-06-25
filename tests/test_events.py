"""Tests for the normalized event-stream projection (orchestrator/events.py).

The projection is the data layer for a future Kanban board. These tests pin:
the EXACT ordered event sequence for a rich State (decisions + a FAILING
held-out + tamper paths + a terminal escalation), provenance fidelity
(decided_by survives), determinism + totality, the merge ordering for --all,
and the read-only `orchestrator events` CLI surface.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from orchestrator.events import (
    EVENT_TYPES,
    Event,
    filter_since,
    merge_events,
    project_events,
)
from orchestrator.main import app
from orchestrator.state import (
    Decision,
    Handover,
    HeldOutRecord,
    IterationUsage,
    State,
    VerifyRecord,
    save_state,
)

runner = CliRunner()

T0 = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=5)
T2 = T0 + timedelta(minutes=6)


def _rich_state(task_id: str = "t1") -> State:
    """A State exercising every board-critical signal at once.

    Two iterations, two decisions of DIFFERENT provenance, an in-tree verify
    PASS, a held-out FAIL (the reward-hack fingerprint), tamper paths, a
    stagnation streak, a handover, and a terminal ESCALATION.
    """
    return State(
        task_id=task_id,
        started_at=T0,
        goal="do the thing",
        iteration=2,
        max_iterations=25,
        repo_remote="git@github.com:marlinjai/orchestrator.git",
        held_out_verify="pytest tests/held_out",
        stakes_tier=2,
        usage=[
            IterationUsage(iteration=1, input_tokens=10, output_tokens=5, model="m"),
            IterationUsage(iteration=2, input_tokens=20, output_tokens=8),
        ],
        decisions=[
            Decision(
                turn=1,
                question="continue?",
                answer="continue",
                reasoning="progress",
                decided_by="proxy",
            ),
            Decision(
                turn=2,
                question="hidden tests red?",
                answer="escalate",
                reasoning="held-out failed",
                decided_by="system",
            ),
        ],
        last_verify=VerifyRecord(
            iteration=2, command="pnpm test", status="pass", exit_code=0, ran_at=T1
        ),
        last_held_out=HeldOutRecord(
            iteration=2,
            command="pytest tests/held_out",
            status="fail",
            exit_code=1,
            ran_at=T2,
        ),
        tamper_paths=["tests/test_a.py"],
        stagnation_streak=2,
        handovers=[Handover(at_turn=1, reason="context full", doc="docs/h.md")],
        status="escalated",
        exit_reason="held-out fingerprint",
    )


def test_exact_ordered_event_sequence():
    """The rich State projects the EXACT expected ordered event types + seq."""
    events = project_events(_rich_state())
    types = [e.type for e in events]
    assert types == [
        "dispatched",
        "iteration",  # iteration 1
        "decision",  # turn 1
        "handover",  # at_turn 1
        "iteration",  # iteration 2
        "decision",  # turn 2
        "verify",
        "held_out",
        "tamper",
        "stagnation",
        "escalation",
        "terminal",
    ]
    # seq is a contiguous 0-based ordinal in stream order.
    assert [e.seq for e in events] == list(range(len(events)))
    # Ordering invariant: (iteration, kind order) is non-decreasing.
    kind = {name: i for i, name in enumerate(EVENT_TYPES)}
    keys = [(e.iteration, kind[e.type]) for e in events]
    assert keys == sorted(keys)
    # Every event is stamped with the owning task and a real timestamp.
    assert all(e.task_id == "t1" for e in events)
    assert all(isinstance(e.ts, datetime) for e in events)


def test_held_out_fail_is_flagged_as_reward_hack():
    """In-tree green + held-out red surfaces the reward-hack fingerprint."""
    events = project_events(_rich_state())
    held = [e for e in events if e.type == "held_out"]
    assert len(held) == 1
    h = held[0]
    assert h.data["status"] == "fail"
    assert h.data["reward_hack_fingerprint"] is True
    assert h.data["decided_by"] == "system"
    assert "REWARD-HACK FINGERPRINT" in h.summary


def test_held_out_fail_without_green_is_not_a_fingerprint():
    """A held-out fail with NO passing in-tree verify is not the fingerprint."""
    state = _rich_state()
    state.last_verify = VerifyRecord(
        iteration=2, command="pnpm test", status="fail", exit_code=1, ran_at=T1
    )
    held = [e for e in project_events(state) if e.type == "held_out"][0]
    assert held.data["reward_hack_fingerprint"] is False
    assert "REWARD-HACK FINGERPRINT" not in held.summary


def test_tamper_and_stagnation_surface():
    events = project_events(_rich_state())
    tamper = [e for e in events if e.type == "tamper"]
    stag = [e for e in events if e.type == "stagnation"]
    assert len(tamper) == 1
    assert tamper[0].data["paths"] == ["tests/test_a.py"]
    assert tamper[0].data["decided_by"] == "system"
    assert len(stag) == 1
    assert stag[0].data["streak"] == 2


def test_decision_provenance_is_preserved():
    """decided_by is NOT flattened: system ground truth stays distinct."""
    decisions = [e for e in project_events(_rich_state()) if e.type == "decision"]
    by = [d.data["decided_by"] for d in decisions]
    assert by == ["proxy", "system"]
    # The provenance is also reflected in the human-readable summary.
    assert "[proxy]" in decisions[0].summary
    assert "[system]" in decisions[1].summary


def test_terminal_and_escalation_carry_exit_reason():
    events = project_events(_rich_state())
    assert events[-1].type == "terminal"
    assert events[-1].data["status"] == "escalated"
    assert events[-1].data["exit_reason"] == "held-out fingerprint"
    esc = [e for e in events if e.type == "escalation"]
    assert len(esc) == 1
    assert esc[0].data["exit_reason"] == "held-out fingerprint"


def test_dispatched_carries_trust_anchor():
    d = project_events(_rich_state())[0]
    assert d.type == "dispatched"
    assert d.iteration == 0
    assert d.data["repo_remote"] == "git@github.com:marlinjai/orchestrator.git"
    assert d.data["held_out_configured"] is True
    assert d.data["stakes_tier"] == 2


def test_projection_is_deterministic():
    a = project_events(_rich_state())
    b = project_events(_rich_state())
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]


def test_projection_is_total_on_minimal_running_state():
    """A bare, still-running State projects with only a dispatched event."""
    events = project_events(State(task_id="bare", goal="g"))
    assert [e.type for e in events] == ["dispatched"]
    # Running => no terminal, no escalation.
    assert all(e.type not in ("terminal", "escalation") for e in events)


def test_stakes_gate_refusal_projects_dispatch_then_terminal():
    """A run refused before any iteration: dispatched + terminal, nothing else."""
    state = State(
        task_id="gated",
        goal="g",
        status="stopped",
        exit_reason="stakes gate",
        iteration=0,
    )
    events = project_events(state)
    assert [e.type for e in events] == ["dispatched", "terminal"]
    assert events[-1].data["exit_reason"] == "stakes gate"


def test_merge_events_is_time_ordered_and_stable():
    """merge_events sorts by (ts, task_id, seq) deterministically."""
    a = project_events(_rich_state("alpha"))
    b = project_events(_rich_state("beta"))
    merged = merge_events(a + b)
    keys = [(e.ts, e.task_id, e.seq) for e in merged]
    assert keys == sorted(keys)
    # Per-task seq is NOT renumbered by the merge.
    assert {e.seq for e in merged if e.task_id == "alpha"} == {e.seq for e in a}


def test_filter_since_keeps_only_later_events():
    events = project_events(_rich_state())
    kept = filter_since(events, T1)
    # Only verify (T1) and held-out (T2) are at/after T1; the started_at-stamped
    # events fall away.
    kept_types = {e.type for e in kept}
    assert "verify" in kept_types
    assert "held_out" in kept_types
    assert "dispatched" not in kept_types


def test_event_data_is_json_serializable():
    for e in project_events(_rich_state()):
        # model_dump_json must round-trip (this is what the CLI emits per line).
        round_tripped = json.loads(e.model_dump_json())
        assert round_tripped["task_id"] == "t1"
        assert isinstance(round_tripped["data"], dict)


# --- CLI surface (read-only) -------------------------------------------------


def _save(home: Path, task_id: str, state: State) -> None:
    task_dir = home / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    save_state(task_dir / "state.json", state)


def test_cli_task_id_emits_valid_jsonl(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    _save(tmp_path, "t1", _rich_state("t1"))
    result = runner.invoke(app, ["events", "--task-id", "t1"])
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["type"] == "dispatched"
    assert parsed[-1]["type"] == "terminal"
    assert all(p["task_id"] == "t1" for p in parsed)
    # Every line is a complete Event (round-trips through the model).
    for p in parsed:
        Event.model_validate(p)


def test_cli_all_merges_and_orders(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    _save(tmp_path, "alpha", _rich_state("alpha"))
    _save(tmp_path, "beta", _rich_state("beta"))
    result = runner.invoke(app, ["events", "--all"])
    assert result.exit_code == 0
    parsed = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    assert {p["task_id"] for p in parsed} == {"alpha", "beta"}
    # Merged stream is time-ordered (ts, task_id, seq).
    keys = [(p["ts"], p["task_id"], p["seq"]) for p in parsed]
    assert keys == sorted(keys)


def test_cli_all_since_filters(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    _save(tmp_path, "t1", _rich_state("t1"))
    result = runner.invoke(
        app, ["events", "--all", "--since", T1.isoformat()]
    )
    assert result.exit_code == 0
    parsed = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    types = {p["type"] for p in parsed}
    assert "verify" in types and "held_out" in types
    assert "dispatched" not in types


def test_cli_all_skips_corrupt_state(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    _save(tmp_path, "good", _rich_state("good"))
    bad_dir = tmp_path / "tasks" / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "state.json").write_text("{ not valid json")
    result = runner.invoke(app, ["events", "--all"])
    assert result.exit_code == 0
    parsed = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    # The good task still emits; the corrupt one is skipped (warning on stderr).
    assert all(p["task_id"] == "good" for p in parsed)


def test_cli_requires_a_selector(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    assert runner.invoke(app, ["events"]).exit_code != 0


def test_cli_rejects_both_selectors(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    result = runner.invoke(app, ["events", "--task-id", "x", "--all"])
    assert result.exit_code != 0


def test_cli_since_requires_all(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    _save(tmp_path, "t1", _rich_state("t1"))
    result = runner.invoke(
        app, ["events", "--task-id", "t1", "--since", T1.isoformat()]
    )
    assert result.exit_code != 0


def test_cli_missing_task_errors(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_HOME", str(tmp_path))
    assert runner.invoke(app, ["events", "--task-id", "nope"]).exit_code != 0
