import subprocess
from pathlib import Path

import pytest

from orchestrator.worktree import (
    add_worktree,
    default_worktree_path,
    is_git_repo,
    list_worktree_paths,
    remove_worktree,
    worktree_branch,
)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "t@example.com"], repo)
    _run(["git", "config", "user.name", "T"], repo)
    _run(["git", "config", "commit.gpgsign", "false"], repo)
    (repo / "seed.txt").write_text("seed\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", "seed"], repo)
    return repo


def _branch_exists(repo: Path, branch: str) -> bool:
    r = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


# --- naming helpers ---

def test_worktree_branch():
    assert worktree_branch("abc") == "orchestrator/abc"


def test_default_worktree_path_is_sibling():
    assert default_worktree_path(Path("/a/b/repo"), "t1") == Path("/a/b/repo-orch-t1")


# --- is_git_repo ---

def test_is_git_repo_true(git_repo: Path):
    assert is_git_repo(git_repo)


def test_is_git_repo_false_for_plain_dir(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not is_git_repo(plain)


def test_is_git_repo_false_for_missing_dir(tmp_path: Path):
    assert not is_git_repo(tmp_path / "nope")


# --- add / list ---

def test_add_worktree_creates_on_branch(git_repo: Path, tmp_path: Path):
    wt = tmp_path / "wt"
    add_worktree(git_repo, wt, "orchestrator/t1")
    assert wt.exists()
    assert str(wt.resolve()) in list_worktree_paths(git_repo)
    assert _branch_exists(git_repo, "orchestrator/t1")


def test_add_worktree_is_idempotent_on_reuse(git_repo: Path, tmp_path: Path):
    wt = tmp_path / "wt"
    add_worktree(git_repo, wt, "orchestrator/t1")
    # second call must not raise: it is an already-registered worktree (resume).
    add_worktree(git_repo, wt, "orchestrator/t1")
    assert wt.exists()


def test_add_worktree_fails_loud_on_stale_dir(git_repo: Path, tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "junk.txt").write_text("not a worktree")
    with pytest.raises(RuntimeError):
        add_worktree(git_repo, wt, "orchestrator/t1")


# --- remove (never --force) ---

def test_remove_clean_worktree_succeeds_and_keeps_branch(git_repo: Path, tmp_path: Path):
    wt = tmp_path / "wt"
    add_worktree(git_repo, wt, "orchestrator/t1")
    # commit work inside the worktree, then leave a clean tree
    (wt / "feature.py").write_text("x = 1\n")
    _run(["git", "add", "-A"], wt)
    _run(["git", "commit", "-q", "-m", "feat"], wt)

    removed, msg = remove_worktree(git_repo, wt)
    assert removed, msg
    assert not wt.exists()
    # committed work survives on the branch, even though the dir is gone
    assert _branch_exists(git_repo, "orchestrator/t1")


def test_remove_dirty_worktree_refuses_and_retains(git_repo: Path, tmp_path: Path):
    wt = tmp_path / "wt"
    add_worktree(git_repo, wt, "orchestrator/t1")
    (wt / "uncommitted.txt").write_text("work in progress\n")  # untracked = dirty

    removed, msg = remove_worktree(git_repo, wt)
    assert not removed
    assert wt.exists()  # never force-removed: the work is retained for the operator
    assert msg
