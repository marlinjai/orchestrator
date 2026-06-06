"""Tests for orchestrator/handover.py: prompt builder, git verifier, seed builder."""

import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.handover import (
    build_handover_prompt,
    is_handover_complete,
    seed_fresh_session_message,
    verify_handover_doc,
)
from orchestrator.state import CommitEntry, Handover, IterationUsage, State


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(
    *,
    baseline_ref: str | None = "abc1234",
    commits: list[CommitEntry] | None = None,
    handovers: list[Handover] | None = None,
    input_tokens: int = 0,
) -> State:
    s = State(task_id="test-task", goal="Do the thing")
    s.baseline_ref = baseline_ref
    if commits:
        s.commits = commits
    if handovers:
        s.handovers = handovers
    if input_tokens:
        s.usage.append(IterationUsage(iteration=1, input_tokens=input_tokens))
    return s


# ---------------------------------------------------------------------------
# is_handover_complete
# ---------------------------------------------------------------------------

def test_handover_complete_marker_detected():
    assert is_handover_complete("Some output\nHANDOVER_COMPLETE\nmore text")


def test_handover_complete_absent():
    assert not is_handover_complete("I wrote the file but forgot the marker")


def test_handover_complete_empty():
    assert not is_handover_complete("")


# ---------------------------------------------------------------------------
# build_handover_prompt
# ---------------------------------------------------------------------------

def test_build_handover_prompt_contains_token_count():
    state = _state(input_tokens=85_000)
    prompt = build_handover_prompt(state)
    assert "85,000" in prompt


def test_build_handover_prompt_shows_leg_number():
    # First handover = leg 1
    state = _state()
    prompt = build_handover_prompt(state)
    assert "leg 1" in prompt

    # Second handover = leg 2
    state.handovers.append(Handover(at_turn=5, reason="x", doc="HANDOVER.md"))
    prompt2 = build_handover_prompt(state)
    assert "leg 2" in prompt2


def test_build_handover_prompt_contains_handover_instructions():
    state = _state()
    prompt = build_handover_prompt(state)
    assert "HANDOVER.md" in prompt
    assert "VERIFIED DONE" in prompt
    assert "NEXT EXACT ACTION" in prompt
    assert "HANDOVER_COMPLETE" in prompt


# ---------------------------------------------------------------------------
# verify_handover_doc
# ---------------------------------------------------------------------------

def _fake_git_log(shas: list[str]):
    """Return a mock for subprocess.run that yields git log output."""
    stdout = "\n".join(shas) + "\n"

    def _run(args, **kwargs):
        class R:
            returncode = 0
            stderr = ""

        r = R()
        r.stdout = stdout
        return r

    return _run


def test_verify_clean_doc(tmp_path):
    full_sha = "a" * 40
    short_sha = full_sha[:8]
    doc = textwrap.dedent(f"""\
        ## VERIFIED DONE
        - SHA: {short_sha}
          Files: src/foo.py
          Summary: add feature
          Tests: passed
    """)
    state = _state(baseline_ref="base123")
    with patch("subprocess.run", side_effect=_fake_git_log([full_sha])):
        result = verify_handover_doc(doc, state, tmp_path)
    assert result == []


def test_verify_detects_invented_sha(tmp_path):
    real_sha = "b" * 40
    fake_sha = "deadbeef"
    doc = textwrap.dedent(f"""\
        ## VERIFIED DONE
        - SHA: {fake_sha}
          Files: x.py
    """)
    state = _state(baseline_ref="base123")
    with patch("subprocess.run", side_effect=_fake_git_log([real_sha])):
        result = verify_handover_doc(doc, state, tmp_path)
    assert any(fake_sha in d for d in result)


def test_verify_detects_unmentioned_real_commit(tmp_path):
    real_sha = "c" * 40
    doc = "## VERIFIED DONE\n(nothing committed yet)\n"
    state = _state(baseline_ref="base123")
    with patch("subprocess.run", side_effect=_fake_git_log([real_sha])):
        result = verify_handover_doc(doc, state, tmp_path)
    assert any(real_sha[:12] in d for d in result)


def test_verify_no_baseline_ref_is_noop(tmp_path):
    state = _state(baseline_ref=None)
    result = verify_handover_doc("anything", state, tmp_path)
    assert result == []


def test_verify_git_log_failure_is_noop(tmp_path):
    def _fail(*args, **kwargs):
        class R:
            returncode = 1
            stdout = ""
            stderr = "not a repo"
        return R()

    state = _state(baseline_ref="base123")
    with patch("subprocess.run", side_effect=_fail):
        result = verify_handover_doc("- SHA: deadbeef\n", state, tmp_path)
    assert result == []


# ---------------------------------------------------------------------------
# seed_fresh_session_message
# ---------------------------------------------------------------------------

def test_seed_contains_doc_contents(tmp_path):
    doc = tmp_path / "HANDOVER.md"
    doc.write_text("## GOAL\nDo the thing\n## NEXT EXACT ACTION\nFix foo.py line 42\n")
    state = _state()
    state.handovers.append(Handover(at_turn=3, reason="test", doc=str(doc)))
    seed = seed_fresh_session_message(doc, state, discrepancies=[])
    assert "Do the thing" in seed
    assert "Fix foo.py line 42" in seed


def test_seed_no_discrepancies_shows_clean(tmp_path):
    doc = tmp_path / "HANDOVER.md"
    doc.write_text("## GOAL\ngoal\n")
    state = _state()
    state.handovers.append(Handover(at_turn=1, reason="t", doc=str(doc)))
    seed = seed_fresh_session_message(doc, state, discrepancies=[])
    assert "no discrepancies" in seed.lower()


def test_seed_discrepancies_appear_in_warning(tmp_path):
    doc = tmp_path / "HANDOVER.md"
    doc.write_text("## GOAL\ngoal\n")
    state = _state()
    state.handovers.append(Handover(at_turn=1, reason="t", doc=str(doc)))
    discrepancies = ["SHA deadbeef not in git log", "Commit abc123 unmentioned"]
    seed = seed_fresh_session_message(doc, state, discrepancies=discrepancies)
    assert "WARNING" in seed
    assert "deadbeef" in seed
    assert "abc123" in seed


def test_seed_includes_leg_number(tmp_path):
    doc = tmp_path / "HANDOVER.md"
    doc.write_text("content\n")
    state = _state()
    state.handovers.append(Handover(at_turn=5, reason="t", doc=str(doc)))
    seed = seed_fresh_session_message(doc, state, discrepancies=[])
    assert "leg 1" in seed
