import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.orchestrator import OrchestratorConfig, run_orchestrator
from orchestrator.proxy import ProxyDecision
from orchestrator.state import IterationUsage, load_state
from orchestrator.worktree import default_worktree_path, worktree_branch


def _turn(text: str, iteration: int = 1, input_tokens: int = 0):
    """The (chunks, usage) 2-tuple _run_one_turn now returns (worker turn only;
    the Decision Proxy is a separate, post-reconcile call in the loop)."""
    return ([text], IterationUsage(iteration=iteration, input_tokens=input_tokens))


def _decision(action: str, text_out: str = "go", reasoning: str = "r"):
    return ProxyDecision(action=action, text=text_out, reasoning=reasoning)


@contextmanager
def _mock_loop(turns, decisions):
    """Patch the Worker turn and the Decision Proxy with aligned side-effects
    (one turn + one decision per iteration)."""
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn, patch(
        "orchestrator.orchestrator.run_proxy_decision"
    ) as mock_proxy:
        mock_turn.side_effect = turns
        mock_proxy.side_effect = decisions
        yield mock_turn, mock_proxy


@pytest.fixture
def task_dir(tmp_path: Path) -> Path:
    (tmp_path / "goals").mkdir()
    (tmp_path / "personas").mkdir()
    (tmp_path / "goals" / "g.md").write_text("test goal")
    (tmp_path / "personas" / "p.md").write_text("test persona")
    return tmp_path


@pytest.fixture
def cfg(task_dir: Path) -> OrchestratorConfig:
    return OrchestratorConfig(
        task_id="test-task",
        goal_file=task_dir / "goals" / "g.md",
        persona_file=task_dir / "personas" / "p.md",
        project_dir=task_dir,
        state_dir=task_dir / ".orchestrator" / "test-task",
        max_iterations=3,
        max_seconds=60,
        # Keep the fleet-wide STOP file + usage ledger inside the tmp tree so a
        # test never reads or writes the real ~/.orchestrator.
        orchestrator_home=task_dir / ".orchestrator",
        # Absent path: never read the dev machine's real repos.toml.
        repos_config=task_dir / "repos.toml",
    )


async def test_orchestrator_writes_initial_state(cfg: OrchestratorConfig):
    with _mock_loop([_turn("worker said done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.task_id == "test-task"
    assert state.goal == "test goal"
    assert state.status == "completed"


async def test_orchestrator_iterates_until_proxy_stops(cfg: OrchestratorConfig):
    with _mock_loop(
        [_turn("t1", 1), _turn("t2", 2), _turn("t3", 3)],
        [_decision("reply", "continue"), _decision("reply", "continue"), _decision("stop", "", "done")],
    ):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.iteration == 3
    assert state.status == "completed"
    assert len(state.usage) == 3


async def test_orchestrator_halts_on_iteration_cap(cfg: OrchestratorConfig):
    cfg.max_iterations = 2
    with _mock_loop(
        [_turn("t1", 1), _turn("t2", 2)],
        [_decision("reply"), _decision("reply")],
    ):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "stopped"
    assert "iteration" in (state.exit_reason or "").lower()


async def test_orchestrator_halts_on_kill_switch(cfg: OrchestratorConfig):
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "STOP").touch()
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "stopped"
    assert "kill" in (state.exit_reason or "").lower()
    mock_turn.assert_not_called()


async def test_orchestrator_halts_on_global_kill(cfg: OrchestratorConfig):
    cfg.orchestrator_home.mkdir(parents=True, exist_ok=True)
    (cfg.orchestrator_home / "GLOBAL_STOP").touch()
    with patch("orchestrator.orchestrator._run_one_turn") as mock_turn:
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "stopped"
    assert "global kill" in (state.exit_reason or "").lower()
    mock_turn.assert_not_called()


async def test_orchestrator_halts_on_usage_cap(cfg: OrchestratorConfig):
    cfg.max_tokens = 50
    with _mock_loop([_turn("t1", 1, input_tokens=100)], [_decision("reply")]):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "stopped"
    assert "usage cap" in (state.exit_reason or "").lower()


async def test_orchestrator_halts_on_daily_token_cap(cfg: OrchestratorConfig):
    cfg.daily_token_cap = 50
    with _mock_loop([_turn("t1", 1, input_tokens=100)], [_decision("reply")]):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "stopped"
    assert "daily token cap" in (state.exit_reason or "").lower()


async def test_orchestrator_halts_on_escalate(cfg: OrchestratorConfig):
    with _mock_loop([_turn("t1")], [_decision("escalate", "need human", "money")]):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "escalated"


async def test_orchestrator_writes_to_log_file(task_dir: Path):
    """When log_path is set, orchestrator output is captured to that file."""
    log_path = task_dir / "run.log"
    cfg = OrchestratorConfig(
        task_id="log-test",
        goal_file=task_dir / "goals" / "g.md",
        persona_file=task_dir / "personas" / "p.md",
        project_dir=task_dir,
        state_dir=task_dir / ".orchestrator" / "log-test",
        max_iterations=2,
        max_seconds=60,
        log_path=log_path,
        orchestrator_home=task_dir / ".orchestrator",
        repos_config=task_dir / "repos.toml",
    )
    with _mock_loop([_turn("worker output")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)
    assert log_path.exists()
    contents = log_path.read_text()
    assert contents.strip(), "expected log file to contain orchestrator output"
    assert "iteration 1" in contents.lower()


async def test_orchestrator_marks_failed_on_sdk_error(cfg: OrchestratorConfig):
    class FakeError(RuntimeError):
        pass

    with patch("orchestrator.orchestrator.ClaudeSDKClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.side_effect = FakeError("auth blew up")
        with pytest.raises(FakeError):
            await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "failed"
    assert "auth blew up" in (state.exit_reason or "")


# ---- verify gate (real subprocess; Worker turn + Proxy mocked) ----


async def test_verify_gate_pass_completes(cfg: OrchestratorConfig):
    cfg.goal_file.write_text('---\nverify: "true"\n---\ndo the thing')
    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "completed"
    assert state.last_verify is not None and state.last_verify.status == "pass"
    assert state.verify_attempts == 0


async def test_verify_gate_failure_escalates_at_cap(cfg: OrchestratorConfig):
    cfg.goal_file.write_text('---\nverify: "exit 1"\n---\ndo the thing')
    with _mock_loop(
        [_turn("done", 1), _turn("done", 2)],
        [_decision("stop", "", "done"), _decision("stop", "", "done")],
    ):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "escalated"
    assert state.verify_attempts == 2  # fix_cap default
    assert state.last_verify is not None and state.last_verify.status == "fail"


async def test_verify_gate_retries_then_completes(cfg: OrchestratorConfig):
    # Fails the first run (sentinel absent), passes the second (sentinel present).
    cfg.goal_file.write_text(
        '---\nverify: "test -f vok || { touch vok; exit 1; }"\n---\ndo the thing'
    )
    with _mock_loop(
        [_turn("done", 1), _turn("done", 2)],
        [_decision("stop", "", "done"), _decision("stop", "", "done")],
    ):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "completed"
    assert state.verify_attempts == 0  # reset on the passing run


async def test_verify_gate_misconfigured_escalates(cfg: OrchestratorConfig):
    cfg.goal_file.write_text('---\nverify: "gh pr merge 1"\n---\ndo the thing')
    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "escalated"
    assert state.last_verify is not None and state.last_verify.status == "misconfigured"


# ---- tamper tripwire (real git repo; Worker turn weakens tests as a side effect) ----


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _repo_with_test(root: Path) -> Path:
    repo = root / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(["git", "init", "-q"], repo)
    _git(["git", "config", "user.email", "t@example.com"], repo)
    _git(["git", "config", "user.name", "T"], repo)
    _git(["git", "config", "commit.gpgsign", "false"], repo)
    (repo / "tests" / "test_a.py").write_text(
        "def test_a():\n    assert 1 == 1\n    assert 2 == 2\n    assert 3 == 3\n"
    )
    _git(["git", "add", "-A"], repo)
    _git(["git", "commit", "-q", "-m", "seed"], repo)
    return repo


def _cfg_for_repo(root: Path, repo: Path, verify: str | None = "true") -> OrchestratorConfig:
    (root / "goals").mkdir(exist_ok=True)
    (root / "personas").mkdir(exist_ok=True)
    goal = root / "goals" / "g.md"
    if verify is None:
        goal.write_text("do the thing")
    else:
        goal.write_text(f'---\nverify: "{verify}"\n---\ndo the thing')
    (root / "personas" / "p.md").write_text("p")
    return OrchestratorConfig(
        task_id="tamper-task",
        goal_file=goal,
        persona_file=root / "personas" / "p.md",
        project_dir=repo,
        state_dir=root / ".orchestrator" / "tamper-task",
        max_iterations=2,
        max_seconds=60,
        orchestrator_home=root / ".orchestrator",
        repos_config=root / "repos.toml",
    )


async def test_tamper_trip_escalates_on_weakened_tests(tmp_path: Path):
    repo = _repo_with_test(tmp_path)
    cfg = _cfg_for_repo(tmp_path, repo)

    def fake_turn(*, client, user_message, state, out_console=None):
        # The "Worker" guts the test to make a red suite green, then claims done.
        (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
        return (["did the thing"], IterationUsage(iteration=state.iteration))

    with patch("orchestrator.orchestrator._run_one_turn", side_effect=fake_turn), patch(
        "orchestrator.orchestrator.run_proxy_decision",
        return_value=ProxyDecision(action="stop", text="", reasoning="done"),
    ):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "escalated"
    assert state.tamper_paths == ["tests/test_a.py"]
    assert "tamper" in (state.exit_reason or "").lower()
    # verify itself passed: the trip is purely the tamper downgrade.
    assert state.last_verify is not None and state.last_verify.status == "pass"


async def test_repo_policy_resolved_onto_state(tmp_path: Path):
    repo = _repo_with_test(tmp_path)
    _git(["git", "remote", "add", "origin", "git@github.com:test/proj.git"], repo)
    cfg = _cfg_for_repo(tmp_path, repo)  # repos_config = tmp_path / "repos.toml"
    (tmp_path / "repos.toml").write_text(
        '[repos."github.com/test/proj"]\n'
        'held_out_verify = "true"\nstakes_tier = 3\n'
    )

    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.repo_remote == "github.com/test/proj"
    assert state.stakes_tier == 3
    assert state.held_out_verify == "true"
    # held-out gate ran and passed, so the run completes
    assert state.status == "completed"
    assert state.last_held_out is not None and state.last_held_out.status == "pass"


async def test_held_out_fail_escalates_after_intree_pass(tmp_path: Path):
    """In-tree verify green but the held-out (out-of-reach) suite red = caught."""
    repo = _repo_with_test(tmp_path)
    _git(["git", "remote", "add", "origin", "git@github.com:test/proj.git"], repo)
    cfg = _cfg_for_repo(tmp_path, repo, verify="true")
    (tmp_path / "repos.toml").write_text(
        '[repos."github.com/test/proj"]\nheld_out_verify = "false"\nstakes_tier = 4\n'
    )

    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "escalated"
    assert state.last_verify is not None and state.last_verify.status == "pass"
    assert state.last_held_out is not None and state.last_held_out.status == "fail"
    assert "reward-hack" in (state.exit_reason or "").lower()


async def test_held_out_as_sole_gate_completes(tmp_path: Path):
    """No in-tree verify, but a held-out command is configured: it runs anyway."""
    repo = _repo_with_test(tmp_path)
    _git(["git", "remote", "add", "origin", "git@github.com:test/proj.git"], repo)
    cfg = _cfg_for_repo(tmp_path, repo, verify=None)
    (tmp_path / "repos.toml").write_text(
        '[repos."github.com/test/proj"]\nheld_out_verify = "true"\n'
    )

    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "completed"
    assert state.last_verify is None  # no in-tree verify ran
    assert state.last_held_out is not None and state.last_held_out.status == "pass"


async def test_held_out_as_sole_gate_fail_escalates(tmp_path: Path):
    repo = _repo_with_test(tmp_path)
    _git(["git", "remote", "add", "origin", "git@github.com:test/proj.git"], repo)
    cfg = _cfg_for_repo(tmp_path, repo, verify=None)
    (tmp_path / "repos.toml").write_text(
        '[repos."github.com/test/proj"]\nheld_out_verify = "false"\n'
    )

    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "escalated"
    assert state.last_held_out is not None and state.last_held_out.status == "fail"
    assert "not trustworthy" in (state.exit_reason or "").lower()


async def test_malformed_registry_fails_run(tmp_path: Path):
    repo = _repo_with_test(tmp_path)
    cfg = _cfg_for_repo(tmp_path, repo)
    (tmp_path / "repos.toml").write_text('[repos."github.com/a/b"]\nstakes_tier = 99\n')

    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "failed"
    assert "repo registry error" in (state.exit_reason or "")


async def test_clean_pass_in_git_repo_completes(tmp_path: Path):
    """A verify pass with the tests left intact must NOT trip the tripwire."""
    repo = _repo_with_test(tmp_path)
    cfg = _cfg_for_repo(tmp_path, repo)

    def fake_turn(*, client, user_message, state, out_console=None):
        # Touches a non-test file only; tests untouched.
        (repo / "feature.py").write_text("x = 1\n")
        return (["did the thing"], IterationUsage(iteration=state.iteration))

    with patch("orchestrator.orchestrator._run_one_turn", side_effect=fake_turn), patch(
        "orchestrator.orchestrator.run_proxy_decision",
        return_value=ProxyDecision(action="stop", text="", reasoning="done"),
    ):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "completed"
    assert state.tamper_paths == []


# ---- brick 4: worktree-per-attempt isolation ----


async def test_worktree_isolation_runs_in_worktree_original_untouched(tmp_path: Path):
    """With isolation on, the Worker edits the worktree, every gate follows the
    worktree (tamper fires there), and the original checkout is never touched."""
    repo = _repo_with_test(tmp_path)
    cfg = _cfg_for_repo(tmp_path, repo)
    cfg.worktree_isolation = True
    wt = default_worktree_path(repo, cfg.task_id)

    def adversary_turn(*, client, user_message, state, out_console=None):
        # The Worker guts the test IN THE WORKTREE (its cwd), not the original.
        (wt / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
        return (["all green"], IterationUsage(iteration=state.iteration))

    with patch("orchestrator.orchestrator._run_one_turn", side_effect=adversary_turn), patch(
        "orchestrator.orchestrator.run_proxy_decision",
        return_value=ProxyDecision(action="stop", text="", reasoning="done"),
    ):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    # the tamper scan ran against the worktree (proves work_dir threading)
    assert state.status == "escalated"
    assert state.tamper_paths == ["tests/test_a.py"]
    # ISOLATION: the original checkout's test file is intact (3 asserts)
    original = (repo / "tests" / "test_a.py").read_text()
    assert original.count("assert") == 3
    # an escalated run retains its worktree for inspection
    assert wt.exists()


async def test_worktree_clean_completion_removes_worktree(tmp_path: Path):
    """A clean completion auto-removes the worktree dir; the work is preserved on
    the attempt branch in the original repo."""
    repo = _repo_with_test(tmp_path)
    cfg = _cfg_for_repo(tmp_path, repo)
    cfg.worktree_isolation = True
    wt = default_worktree_path(repo, cfg.task_id)

    def good_turn(*, client, user_message, state, out_console=None):
        (wt / "feature.py").write_text("x = 1\n")
        _git(["git", "add", "-A"], wt)
        _git(["git", "commit", "-q", "-m", "feat: add feature"], wt)
        return (["shipped"], IterationUsage(iteration=state.iteration))

    with patch("orchestrator.orchestrator._run_one_turn", side_effect=good_turn), patch(
        "orchestrator.orchestrator.run_proxy_decision",
        return_value=ProxyDecision(action="stop", text="", reasoning="done"),
    ):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "completed"
    # clean worktree is removed...
    assert not wt.exists()
    # ...but the attempt branch (with the commit) survives in the original repo
    branches = subprocess.run(
        ["git", "branch", "--list", worktree_branch(cfg.task_id)],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout
    assert worktree_branch(cfg.task_id) in branches


async def test_worktree_flag_on_non_git_falls_back_in_place(tmp_path: Path, task_dir: Path):
    """Isolation requested on a non-git project falls back to running in place
    rather than failing; no worktree is created."""
    cfg = OrchestratorConfig(
        task_id="nogit",
        goal_file=task_dir / "goals" / "g.md",
        persona_file=task_dir / "personas" / "p.md",
        project_dir=task_dir,  # not a git repo
        state_dir=task_dir / ".orchestrator" / "nogit",
        max_iterations=2,
        max_seconds=60,
        orchestrator_home=task_dir / ".orchestrator",
        worktree_isolation=True,
    )
    with _mock_loop([_turn("done")], [_decision("stop", text_out="", reasoning="done")]):
        await run_orchestrator(cfg)
    state = load_state(cfg.state_dir / "state.json")
    assert state.status == "completed"
    assert not default_worktree_path(task_dir, "nogit").exists()
