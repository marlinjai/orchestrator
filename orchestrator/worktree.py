"""Worktree-per-attempt isolation (Wave 2 of the verifier track).

Run a Worker attempt in its own git worktree so a bad attempt is throwaway and
the operator's real checkout is never touched. Ships as N=1 collision-prevention
behind a flag, with a fallback to running in place (NOT "this makes best-of-N
safe", which needs more).

The load-bearing rule (roadmap Wave 2): every tree-touching operation
(baseline_ref, reconcile, the verify gate, the tamper scan, the held-out gate,
and the Worker's cwd) must follow the SAME directory, or you silently verify a
different tree than the Worker edited. run_orchestrator computes one ``work_dir``
at run start and threads it everywhere, so there is no mid-run repoint to get
wrong.

Cleanup never loses work. ``git worktree remove`` refuses on a dirty or
untracked tree, and we NEVER pass ``--force``. Committed work survives removal:
it lives on the attempt branch in the shared repo, not in the worktree dir. A
run that needs human eyes (escalated / failed) keeps its worktree for inspection
(see ``orchestrator-worktree-merge-cleanup-order``).
"""

import subprocess
from pathlib import Path

_GIT_TIMEOUT_S = 15


def worktree_branch(task_id: str) -> str:
    """The attempt branch a task's worktree checks out. The deliverable: it holds
    the attempt's commits and survives worktree removal."""
    return f"orchestrator/{task_id}"


def default_worktree_path(project_dir: Path, task_id: str) -> Path:
    """Sibling path for a task's worktree (matches the operator batch convention
    `../<repo>-orch-<slug>`). Outside the repo, so git accepts it."""
    project_dir = Path(project_dir)
    return project_dir.parent / f"{project_dir.name}-orch-{task_id}"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=_GIT_TIMEOUT_S,
    )


def is_git_repo(project_dir: Path) -> bool:
    try:
        result = _run(["git", "rev-parse", "--is-inside-work-tree"], project_dir)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def list_worktree_paths(repo_dir: Path) -> set[str]:
    """Resolved absolute paths of every worktree registered for ``repo_dir``."""
    try:
        result = _run(["git", "worktree", "list", "--porcelain"], repo_dir)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            raw = line[len("worktree ") :].strip()
            if raw:
                paths.add(str(Path(raw).resolve()))
    return paths


def _branch_exists(repo_dir: Path, branch: str) -> bool:
    try:
        result = _run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
            repo_dir,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def add_worktree(
    repo_dir: Path, worktree_path: Path, branch: str, base_ref: str = "HEAD"
) -> None:
    """Create the attempt worktree, or reuse it if it already exists (resume).

    Idempotent for the resume case: if ``worktree_path`` is already a registered
    worktree, this is a no-op. Otherwise it adds the worktree, creating ``branch``
    from ``base_ref`` when the branch is new or checking out the existing branch.
    Raises RuntimeError on any other failure (e.g. a stale, unregistered dir at
    the path), so the caller fails loud rather than surprise-editing the real
    checkout.
    """
    worktree_path = Path(worktree_path)
    if str(worktree_path.resolve()) in list_worktree_paths(repo_dir):
        return  # already a registered worktree: reuse it
    if _branch_exists(repo_dir, branch):
        args = ["git", "worktree", "add", str(worktree_path), branch]
    else:
        args = ["git", "worktree", "add", "-b", branch, str(worktree_path), base_ref]
    try:
        result = _run(args, repo_dir)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"git worktree add failed: {e}") from e
    if result.returncode != 0:
        raise RuntimeError(
            "git worktree add failed: "
            + (result.stderr.strip() or result.stdout.strip() or "unknown error")
        )


def remove_worktree(repo_dir: Path, worktree_path: Path) -> tuple[bool, str]:
    """Remove the worktree dir, NEVER with --force.

    Returns ``(removed, message)``. git refuses on a dirty / untracked tree, so a
    False return means uncommitted or untracked work is present and the dir is
    retained for the operator to reconcile. Committed work is unaffected either
    way: it lives on the attempt branch, not in the dir.
    """
    try:
        result = _run(["git", "worktree", "remove", str(worktree_path)], repo_dir)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"git worktree remove errored: {e}"
    if result.returncode == 0:
        return True, "removed"
    return False, (
        result.stderr.strip() or result.stdout.strip() or "git worktree remove failed"
    )
