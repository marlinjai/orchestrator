import subprocess
from pathlib import Path

import pytest

from orchestrator.reconcile import git_head, reconcile
from orchestrator.state import CommitEntry, FileTouched, State


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "t@example.com"], repo)
    _run(["git", "config", "user.name", "T"], repo)
    _run(["git", "config", "commit.gpgsign", "false"], repo)
    (repo / "seed.txt").write_text("seed\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "seed"], repo)
    return repo


def test_git_head_returns_sha(git_repo: Path):
    sha = git_head(git_repo)
    assert sha is not None and len(sha) == 40


def test_git_head_returns_none_outside_repo(tmp_path: Path):
    assert git_head(tmp_path) is None


def test_reconcile_noop_without_baseline(git_repo: Path):
    state = State(task_id="t", goal="g")
    assert state.baseline_ref is None
    added = reconcile(state, git_repo)
    assert added == (0, 0)


def test_reconcile_backfills_unreported_commit(git_repo: Path):
    baseline = git_head(git_repo)
    state = State(task_id="t", goal="g", baseline_ref=baseline)
    # Simulate Worker committing without calling update_state(kind="commit").
    (git_repo / "new.py").write_text("x = 1\n")
    _run(["git", "add", "."], git_repo)
    _run(["git", "commit", "-q", "-m", "feat: added new file"], git_repo)

    commits_added, files_added = reconcile(state, git_repo)
    assert commits_added == 1
    assert files_added == 1
    assert state.commits[0].decided_by == "system"
    assert state.commits[0].message == "feat: added new file"
    assert state.files_touched[0].path == "new.py"
    assert state.files_touched[0].decided_by == "system"


def test_reconcile_preserves_worker_reported_entries(git_repo: Path):
    """Worker-reported entries (decided_by=proxy) must not be dropped or
    re-stamped when reconciliation runs against the same shas/paths."""
    baseline = git_head(git_repo)
    (git_repo / "f.py").write_text("y = 2\n")
    _run(["git", "add", "."], git_repo)
    _run(["git", "commit", "-q", "-m", "feat: f"], git_repo)
    new_sha = git_head(git_repo)

    state = State(
        task_id="t",
        goal="g",
        baseline_ref=baseline,
        commits=[CommitEntry(sha=new_sha, message="feat: f", decided_by="proxy")],
        files_touched=[FileTouched(path="f.py", decided_by="proxy")],
    )

    commits_added, files_added = reconcile(state, git_repo)
    assert commits_added == 0
    assert files_added == 0
    assert state.commits[0].decided_by == "proxy"
    assert state.files_touched[0].decided_by == "proxy"


def test_reconcile_mixed_reported_and_unreported(git_repo: Path):
    baseline = git_head(git_repo)
    (git_repo / "a.py").write_text("a = 1\n")
    _run(["git", "add", "."], git_repo)
    _run(["git", "commit", "-q", "-m", "feat: a"], git_repo)
    sha_a = git_head(git_repo)
    (git_repo / "b.py").write_text("b = 2\n")
    _run(["git", "add", "."], git_repo)
    _run(["git", "commit", "-q", "-m", "feat: b"], git_repo)

    state = State(
        task_id="t",
        goal="g",
        baseline_ref=baseline,
        commits=[CommitEntry(sha=sha_a, message="feat: a", decided_by="proxy")],
    )
    commits_added, files_added = reconcile(state, git_repo)
    assert commits_added == 1  # sha_b backfilled
    assert files_added == 2  # both files backfilled
    by_provenance = {c.decided_by for c in state.commits}
    assert by_provenance == {"proxy", "system"}


def test_reconcile_dedup_handles_short_sha_from_worker(git_repo: Path):
    """The Worker often self-reports a short sha (e.g. 7 chars) via
    update_state, while `git log` returns full 40-char shas. The dedup must
    treat them as the same commit, not double-count."""
    baseline = git_head(git_repo)
    (git_repo / "x.py").write_text("x\n")
    _run(["git", "add", "."], git_repo)
    _run(["git", "commit", "-q", "-m", "feat: x"], git_repo)
    full_sha = git_head(git_repo)
    short_sha = full_sha[:7]

    state = State(
        task_id="t",
        goal="g",
        baseline_ref=baseline,
        # Worker self-reported the short sha
        commits=[CommitEntry(sha=short_sha, message="feat: x", decided_by="proxy")],
    )
    commits_added, _ = reconcile(state, git_repo)
    assert commits_added == 0, "short-sha + full-sha should dedupe"
    assert len(state.commits) == 1
    assert state.commits[0].decided_by == "proxy"


def test_reconcile_includes_uncommitted_files(git_repo: Path):
    """A Worker that edits without committing should still show up in
    files_touched so the Proxy sees the activity."""
    baseline = git_head(git_repo)
    (git_repo / "untracked.py").write_text("z = 3\n")
    (git_repo / "seed.txt").write_text("modified\n")

    state = State(task_id="t", goal="g", baseline_ref=baseline)
    commits_added, files_added = reconcile(state, git_repo)
    assert commits_added == 0
    paths = {f.path for f in state.files_touched}
    assert "untracked.py" in paths
    assert "seed.txt" in paths
