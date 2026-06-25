"""Tests for best-of-N (Wave 2 leaf L8).

The per-attempt runner (`orchestrator.best_of._run_attempt`) is MOCKED in every
test so the suite never spawns a real Worker. The repo-policy + git-repo gate
helpers are monkeypatched too, so no test touches a real registry or git tree.

What these prove:
- selection picks the held-out-green attempt with the LOWEST time_to_verified,
  NOT the one with the greenest / fastest in-tree verify;
- a cohort with zero held-out-green escalates (no selection);
- the no-held-out-configured case REFUSES before running any attempt;
- a held-out fail is never fed back as a Worker retry (runner called exactly N
  times, each on a distinct, isolated attempt cfg).
"""

from pathlib import Path

import pytest

from orchestrator import best_of as bo
from orchestrator.best_of import CohortResult, run_best_of_n, time_to_verified_ms
from orchestrator.orchestrator import OrchestratorConfig
from orchestrator.repo_registry import RepoPolicy
from orchestrator.state import HeldOutRecord, IterationUsage, State, VerifyRecord, load_state


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _cfg(tmp_path: Path, *, held_out_override: str | None = None) -> OrchestratorConfig:
    """A base config for a best-of cohort. The goal / persona files and project
    dir are never read in the mocked path (run_orchestrator + the gate helpers
    are all monkeypatched), so they need not exist."""
    state_dir = tmp_path / ".orchestrator" / "tasks" / "boN"
    return OrchestratorConfig(
        task_id="boN",
        goal_file=tmp_path / "g.md",
        persona_file=tmp_path / "p.md",
        project_dir=tmp_path / "repo",
        state_dir=state_dir,
        orchestrator_home=tmp_path / ".orchestrator",
        repos_config=tmp_path / "repos.toml",
        held_out_override=held_out_override,
    )


def _state(
    task_id: str,
    *,
    status: str,
    held_out: str | None = None,
    verify: str | None = None,
    ttv_ms: int = 0,
) -> State:
    """A synthetic terminal State. ``ttv_ms`` is the attempt's total
    worker+proxy wall-clock (its time_to_verified_result). ``verify`` is the
    in-tree verify result (present ONLY to prove selection ignores it)."""
    s = State(task_id=task_id, goal="g", status=status)  # type: ignore[arg-type]
    s.usage = [IterationUsage(iteration=1, worker_ms=ttv_ms, proxy_ms=0)]
    if held_out is not None:
        s.last_held_out = HeldOutRecord(
            iteration=1, command="held-out", status=held_out  # type: ignore[arg-type]
        )
    if verify is not None:
        s.last_verify = VerifyRecord(
            iteration=1, command="verify", status=verify  # type: ignore[arg-type]
        )
    return s


class _FakeRunner:
    """Replaces ``_run_attempt``: returns a prepared terminal State per call and
    records the attempt cfgs it was handed (to assert isolation + call count).
    The State's shape is taken from ``specs[index]`` and built with the attempt's
    own task_id so the returned state is faithful to the cfg it ran."""

    def __init__(self, specs: list[dict]):
        self.specs = specs
        self.calls: list[OrchestratorConfig] = []

    async def __call__(self, attempt_cfg: OrchestratorConfig) -> State:
        index = len(self.calls)
        self.calls.append(attempt_cfg)
        spec = self.specs[index]
        return _state(attempt_cfg.task_id, **spec)


@pytest.fixture
def held_out_repo(monkeypatch):
    """Default gate posture: a git repo whose registry policy enforces a held-out
    verify (so best-of-N is allowed to run)."""
    monkeypatch.setattr(bo, "is_git_repo", lambda _p: True)
    monkeypatch.setattr(
        bo,
        "resolve_repo_policy",
        lambda _p, _c: RepoPolicy(remote="h/o/r", held_out_verify="run-hidden", source="registry"),
    )


# --------------------------------------------------------------------------- #
# Selection: held-out-certified, never in-tree-verify
# --------------------------------------------------------------------------- #


async def test_selection_picks_held_out_green_lowest_ttv_not_in_tree_green(
    tmp_path, monkeypatch, held_out_repo
):
    """attempt-0 is the FASTEST and in-tree-GREEN, but its held-out gate FAILED
    (reward-hack fingerprint), so it must NOT win. The winner is the held-out-
    green attempt with the lowest time_to_verified, proving selection is
    held-out-certified, never by the Worker-visible in-tree verify."""
    runner = _FakeRunner(
        [
            # in-tree green + fastest, but held-out RED -> excluded
            {"status": "escalated", "verify": "pass", "held_out": "fail", "ttv_ms": 10},
            {"status": "completed", "verify": "pass", "held_out": "pass", "ttv_ms": 300},
            {"status": "completed", "verify": "pass", "held_out": "pass", "ttv_ms": 100},
        ]
    )
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path), 3)

    assert result.status == "completed"
    # The slower held-out-green attempt-2 wins, NOT the fast in-tree-green attempt-0.
    assert result.selected_branch == "orchestrator/boN-attempt-2"
    assert result.attempts[2].selected is True
    assert result.attempts[0].selected is False  # fast + in-tree-green but held-out-red
    assert result.attempts[1].selected is False  # held-out-green but slower
    # The excluded attempt-0 really was in-tree green and the fastest, so the
    # only reason it lost is the held-out gate.
    assert result.attempts[0].time_to_verified_ms == 10
    assert result.attempts[0].held_out == "fail"


async def test_tie_break_is_lowest_attempt_index(tmp_path, monkeypatch, held_out_repo):
    """Two held-out-green attempts with identical time_to_verified: the lower
    attempt index wins (deterministic tie-break)."""
    runner = _FakeRunner(
        [
            {"status": "completed", "held_out": "pass", "ttv_ms": 50},
            {"status": "completed", "held_out": "pass", "ttv_ms": 50},
        ]
    )
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path), 2)

    assert result.status == "completed"
    assert result.selected_branch == "orchestrator/boN-attempt-0"
    assert result.attempts[0].selected is True
    assert result.attempts[1].selected is False


# --------------------------------------------------------------------------- #
# Zero held-out-green -> escalate (no selection)
# --------------------------------------------------------------------------- #


async def test_zero_held_out_green_escalates_without_selecting(
    tmp_path, monkeypatch, held_out_repo
):
    """When no attempt is held-out-green, the cohort escalates and selects
    nothing, even though an in-tree verify passed."""
    runner = _FakeRunner(
        [
            {"status": "escalated", "verify": "pass", "held_out": "fail", "ttv_ms": 20},
            {"status": "escalated", "verify": "pass", "held_out": "fail", "ttv_ms": 30},
        ]
    )
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path), 2)

    assert result.status == "escalated"
    assert result.selected_branch is None
    assert all(a.selected is False for a in result.attempts)
    assert "no attempt was held-out-green" in result.reason
    # The attempts DID run (this is not the refusal path): N runner calls.
    assert len(runner.calls) == 2


# --------------------------------------------------------------------------- #
# Hard gate: no held-out resolvable -> refuse BEFORE any attempt
# --------------------------------------------------------------------------- #


async def test_no_held_out_configured_refuses_before_running_attempts(
    tmp_path, monkeypatch
):
    """No registry held_out_verify AND no --held-out override: refuse up front,
    run ZERO attempts. The load-bearing safety property."""
    monkeypatch.setattr(bo, "is_git_repo", lambda _p: True)
    monkeypatch.setattr(
        bo, "resolve_repo_policy", lambda _p, _c: RepoPolicy(remote="h/o/r", source="default")
    )
    runner = _FakeRunner([])  # would IndexError if called
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path), 3)

    assert result.status == "escalated"
    assert result.selected_branch is None
    assert result.attempts == []
    assert "requires a held-out verifier" in result.reason
    assert len(runner.calls) == 0  # no attempt was ever launched


async def test_held_out_override_makes_it_resolvable(tmp_path, monkeypatch):
    """An ad-hoc --held-out override satisfies the gate even with no registry
    held_out_verify, and the cohort runs + selects normally."""
    monkeypatch.setattr(bo, "is_git_repo", lambda _p: True)
    monkeypatch.setattr(
        bo, "resolve_repo_policy", lambda _p, _c: RepoPolicy(remote="h/o/r", source="default")
    )
    runner = _FakeRunner([{"status": "completed", "held_out": "pass", "ttv_ms": 5}])
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path, held_out_override="python check.py"), 1)

    assert result.status == "completed"
    assert result.selected_branch == "orchestrator/boN-attempt-0"
    assert len(runner.calls) == 1


async def test_non_git_repo_refuses(tmp_path, monkeypatch):
    """best-of-N needs worktrees for per-attempt isolation; a non-git project is
    refused (failed) and runs zero attempts."""
    monkeypatch.setattr(bo, "is_git_repo", lambda _p: False)
    runner = _FakeRunner([])
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path, held_out_override="python check.py"), 3)

    assert result.status == "failed"
    assert result.attempts == []
    assert "git repo" in result.reason
    assert len(runner.calls) == 0


async def test_malformed_registry_fails_loud(tmp_path, monkeypatch):
    """A malformed registry surfaces as a failed cohort with a clear reason, not
    a silently-disarmed gate."""
    monkeypatch.setattr(bo, "is_git_repo", lambda _p: True)

    def _boom(_p, _c):
        raise ValueError("repos.toml malformed")

    monkeypatch.setattr(bo, "resolve_repo_policy", _boom)
    runner = _FakeRunner([])
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path), 2)

    assert result.status == "failed"
    assert "repo registry error" in result.reason
    assert len(runner.calls) == 0


# --------------------------------------------------------------------------- #
# A held-out fail is never a Worker retry
# --------------------------------------------------------------------------- #


async def test_held_out_fail_is_never_retried(tmp_path, monkeypatch, held_out_repo):
    """A held-out fail only REMOVES that attempt from selection; it is never fed
    back as a retry. The runner is invoked EXACTLY N times (one per attempt
    index), never re-invoked for the failed attempt."""
    runner = _FakeRunner(
        [
            {"status": "completed", "held_out": "pass", "ttv_ms": 200},
            {"status": "escalated", "verify": "pass", "held_out": "fail", "ttv_ms": 10},
            {"status": "completed", "held_out": "pass", "ttv_ms": 150},
        ]
    )
    monkeypatch.setattr(bo, "_run_attempt", runner)

    result = await run_best_of_n(_cfg(tmp_path), 3)

    # Exactly N calls: no extra dispatch for the failed attempt.
    assert len(runner.calls) == 3
    # Each call was a distinct, isolated attempt (no task_id re-dispatched).
    task_ids = [c.task_id for c in runner.calls]
    assert task_ids == ["boN-attempt-0", "boN-attempt-1", "boN-attempt-2"]
    assert len(set(task_ids)) == 3
    # The held-out-green attempt with the lower ttv (attempt-2, 150) wins.
    assert result.selected_branch == "orchestrator/boN-attempt-2"
    assert result.attempts[1].selected is False  # the held-out-fail attempt


# --------------------------------------------------------------------------- #
# Per-attempt isolation
# --------------------------------------------------------------------------- #


async def test_attempts_are_isolated(tmp_path, monkeypatch, held_out_repo):
    """Each attempt cfg is fully isolated: distinct task_id, distinct state dir
    (sibling of the base), forced worktree isolation, and a distinct branch."""
    runner = _FakeRunner([{"status": "completed", "held_out": "pass", "ttv_ms": 1}] * 3)
    monkeypatch.setattr(bo, "_run_attempt", runner)
    base = _cfg(tmp_path)

    await run_best_of_n(base, 3)

    state_dirs = {c.state_dir for c in runner.calls}
    assert len(state_dirs) == 3  # all distinct
    for k, c in enumerate(runner.calls):
        assert c.task_id == f"boN-attempt-{k}"
        assert c.worktree_isolation is True  # mandatory per-attempt isolation
        assert c.state_dir == base.state_dir.parent / f"boN-attempt-{k}"
        assert c.log_path == c.state_dir / "run.log"
        # Caps + trust knobs inherited unchanged from the base cfg.
        assert c.orchestrator_home == base.orchestrator_home
        assert c.repos_config == base.repos_config


# --------------------------------------------------------------------------- #
# Typed cohort record persisted for the board
# --------------------------------------------------------------------------- #


async def test_cohort_record_is_typed_and_persisted(tmp_path, monkeypatch, held_out_repo):
    """run_best_of_n returns a typed CohortResult and writes cohort.json to the
    base state dir, re-loadable against the same model."""
    runner = _FakeRunner(
        [
            {"status": "completed", "held_out": "pass", "ttv_ms": 80},
            {"status": "completed", "held_out": "pass", "ttv_ms": 40},
        ]
    )
    monkeypatch.setattr(bo, "_run_attempt", runner)
    cfg = _cfg(tmp_path)

    result = await run_best_of_n(cfg, 2)

    assert isinstance(result, CohortResult)
    assert result.n == 2
    assert len(result.attempts) == 2
    # Per-attempt record carries the board-facing fields.
    a = result.attempts[1]
    assert a.attempt_index == 1
    assert a.branch == "orchestrator/boN-attempt-1"
    assert a.held_out == "pass"
    assert a.time_to_verified_ms == 40
    assert a.selected is True

    cohort_path = cfg.state_dir / "cohort.json"
    assert cohort_path.exists()
    reloaded = CohortResult.model_validate_json(cohort_path.read_text())
    assert reloaded.selected_branch == "orchestrator/boN-attempt-1"


def test_time_to_verified_ms_sums_worker_and_proxy():
    """The selection metric is the sum of every iteration's worker_ms+proxy_ms."""
    s = State(task_id="t", goal="g")
    s.usage = [
        IterationUsage(iteration=1, worker_ms=100, proxy_ms=20),
        IterationUsage(iteration=2, worker_ms=50, proxy_ms=5),
    ]
    assert time_to_verified_ms(s) == 175


async def test_run_attempt_loads_terminal_state(tmp_path, monkeypatch, held_out_repo):
    """The real _run_attempt seam runs run_orchestrator then loads the terminal
    state. We stub run_orchestrator to write a terminal state.json and assert the
    loaded State flows through into the cohort (proves the seam, no Worker)."""
    import orchestrator.orchestrator as orch
    from orchestrator.state import save_state

    async def _fake_run(attempt_cfg):
        s = State(task_id=attempt_cfg.task_id, goal="g", status="completed")
        s.last_held_out = HeldOutRecord(iteration=1, command="ho", status="pass")
        s.usage = [IterationUsage(iteration=1, worker_ms=7, proxy_ms=0)]
        save_state(attempt_cfg.state_dir / "state.json", s)

    monkeypatch.setattr(orch, "run_orchestrator", _fake_run)
    # Do NOT monkeypatch bo._run_attempt here: exercise the real seam.

    result = await run_best_of_n(_cfg(tmp_path), 1)

    assert result.status == "completed"
    assert result.attempts[0].held_out == "pass"
    assert result.attempts[0].time_to_verified_ms == 7
    # The loaded terminal state was persisted by the (stubbed) run.
    loaded = load_state(_cfg(tmp_path).state_dir.parent / "boN-attempt-0" / "state.json")
    assert loaded.status == "completed"
