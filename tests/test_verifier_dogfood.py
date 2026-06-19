"""Verifier-track capstone: the held-out gate catches a real regression the
visible suite misses, end to end on real artifacts.

This is the repeatable, autonomous form of the dogfood the roadmap calls for
(gate (a): the held-out verifier exists AND is validated on a real repo). It
uses a THROWAWAY sample repo + a throwaway operator vault, never Marlin's real
trust-root, so it runs in CI without any operator setup. The real-repo, real-
hidden-tests version (which repo is high-stakes, where its vault lives) stays
Marlin's call.

What it proves, with all four bricks composed and nothing mocked but the Worker:
- brick 1: the policy resolves from the repo's REAL git remote, and the held-out
  command is sourced from the operator registry, never the goal file;
- brick 2: in-tree verify GREEN + held-out RED == the reward-hack fingerprint;
- brick 3: (ceiling not exercised here; covered in test_worker.py);
- brick 4: the whole run happens in an isolated worktree, and a regressing
  attempt is retained for inspection.

The regression is the case the held-out verifier exists FOR: not test-tampering
(the tamper tripwire already covers that), but a behavioral bug that slips past a
weak in-tree test yet fails a stricter test the Worker could not see.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from orchestrator.orchestrator import OrchestratorConfig, run_orchestrator
from orchestrator.proxy import ProxyDecision
from orchestrator.state import IterationUsage, load_state
from orchestrator.worktree import default_worktree_path


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


# A tiny module whose self-importing test runs against whatever the worktree's
# current working directory holds, so the in-tree and held-out checks both
# exercise the Worker's actual code.
_IMPORT_PRELUDE = "import sys, os\nsys.path.insert(0, os.getcwd())\nimport app\n"


async def test_held_out_catches_regression_visible_suite_misses(tmp_path: Path):
    repo = tmp_path / "sample"
    (repo / "tests").mkdir(parents=True)
    _git(["git", "init", "-q"], repo)
    _git(["git", "config", "user.email", "t@example.com"], repo)
    _git(["git", "config", "user.name", "T"], repo)
    _git(["git", "config", "commit.gpgsign", "false"], repo)
    # a REAL remote: the registry resolves by this, un-fakeable by the goal file
    _git(["git", "remote", "add", "origin", "https://github.com/dogfood/sample.git"], repo)
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n")
    # WEAK in-tree test: only checks the 1,1 case, so a wrong impl can pass it
    (repo / "tests" / "test_app.py").write_text(
        _IMPORT_PRELUDE + "assert app.add(1, 1) == 2\nprint('in-tree OK')\n"
    )
    _git(["git", "add", "-A"], repo)
    _git(["git", "commit", "-q", "-m", "seed"], repo)

    # operator vault OUTSIDE the repo: the strict hidden test the Worker can't see
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "check.py").write_text(
        _IMPORT_PRELUDE
        + "assert app.add(2, 3) == 5\nassert app.add(0, 0) == 0\nprint('held-out OK')\n"
    )

    # operator registry keyed by the REAL remote; held-out command is operator-sourced
    repos_toml = tmp_path / "repos.toml"
    repos_toml.write_text(
        '[repos."github.com/dogfood/sample"]\n'
        f'held_out_verify = "{sys.executable} {vault / "check.py"}"\n'
        "stakes_tier = 2\n"
    )

    goals = tmp_path / "goals"
    goals.mkdir()
    goal = goals / "g.md"
    goal.write_text(
        f'---\nverify: "{sys.executable} tests/test_app.py"\n---\nimplement add'
    )
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "p.md").write_text("p")

    cfg = OrchestratorConfig(
        task_id="dogfood",
        goal_file=goal,
        persona_file=personas / "p.md",
        project_dir=repo,
        state_dir=tmp_path / ".orchestrator" / "dogfood",
        max_iterations=2,
        max_seconds=120,
        orchestrator_home=tmp_path / ".orchestrator",
        repos_config=repos_toml,
        worktree_isolation=True,
    )
    wt = default_worktree_path(repo, "dogfood")

    def regressing_turn(*, client, user_message, state, out_console=None):
        # Passes the weak in-tree test (add(1,1)==2) but is wrong everywhere else.
        # Not test-tampering: the tests are untouched, the CODE is subtly broken.
        (wt / "app.py").write_text("def add(a, b):\n    return a + b if a == 1 else 0\n")
        return (["implemented add"], IterationUsage(iteration=state.iteration))

    with patch("orchestrator.orchestrator._run_one_turn", side_effect=regressing_turn), patch(
        "orchestrator.orchestrator.run_proxy_decision",
        return_value=ProxyDecision(action="stop", text="", reasoning="done"),
    ):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    # the visible suite was GREEN...
    assert state.last_verify is not None and state.last_verify.status == "pass"
    # ...but the out-of-reach suite was RED: the fingerprint fires.
    assert state.last_held_out is not None and state.last_held_out.status == "fail"
    assert state.status == "escalated"
    assert "REWARD-HACK FINGERPRINT" in (state.exit_reason or "")
    # the policy came from the real remote, the held-out command from the registry
    assert state.repo_remote == "github.com/dogfood/sample"
    assert state.stakes_tier == 2
    # the whole attempt ran in the worktree, retained for inspection on escalate
    assert wt.exists()


async def test_held_out_passes_completes_when_code_is_correct(tmp_path: Path):
    """The corroborating case: a correct implementation passes BOTH the visible
    and the hidden suite, so the held-out gate completes rather than escalates."""
    repo = tmp_path / "sample"
    (repo / "tests").mkdir(parents=True)
    _git(["git", "init", "-q"], repo)
    _git(["git", "config", "user.email", "t@example.com"], repo)
    _git(["git", "config", "user.name", "T"], repo)
    _git(["git", "config", "commit.gpgsign", "false"], repo)
    _git(["git", "remote", "add", "origin", "https://github.com/dogfood/sample.git"], repo)
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "tests" / "test_app.py").write_text(
        _IMPORT_PRELUDE + "assert app.add(1, 1) == 2\n"
    )
    _git(["git", "add", "-A"], repo)
    _git(["git", "commit", "-q", "-m", "seed"], repo)

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "check.py").write_text(
        _IMPORT_PRELUDE + "assert app.add(2, 3) == 5\nassert app.add(0, 0) == 0\n"
    )
    repos_toml = tmp_path / "repos.toml"
    repos_toml.write_text(
        '[repos."github.com/dogfood/sample"]\n'
        f'held_out_verify = "{sys.executable} {vault / "check.py"}"\n'
    )
    goals = tmp_path / "goals"
    goals.mkdir()
    goal = goals / "g.md"
    goal.write_text(f'---\nverify: "{sys.executable} tests/test_app.py"\n---\nimplement add')
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "p.md").write_text("p")

    cfg = OrchestratorConfig(
        task_id="dogfood-ok",
        goal_file=goal,
        persona_file=personas / "p.md",
        project_dir=repo,
        state_dir=tmp_path / ".orchestrator" / "dogfood-ok",
        max_iterations=2,
        max_seconds=120,
        orchestrator_home=tmp_path / ".orchestrator",
        repos_config=repos_toml,
        worktree_isolation=True,
    )

    def correct_turn(*, client, user_message, state, out_console=None):
        # leaves the correct impl in place, commits so the worktree is clean
        wt = default_worktree_path(repo, "dogfood-ok")
        _git(["git", "commit", "-q", "--allow-empty", "-m", "noop"], wt)
        return (["looks done"], IterationUsage(iteration=state.iteration))

    with patch("orchestrator.orchestrator._run_one_turn", side_effect=correct_turn), patch(
        "orchestrator.orchestrator.run_proxy_decision",
        return_value=ProxyDecision(action="stop", text="", reasoning="done"),
    ):
        await run_orchestrator(cfg)

    state = load_state(cfg.state_dir / "state.json")
    assert state.last_verify is not None and state.last_verify.status == "pass"
    assert state.last_held_out is not None and state.last_held_out.status == "pass"
    assert state.status == "completed"
