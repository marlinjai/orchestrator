"""Post-iteration reconciliation: detect commits and file edits the Worker did
not self-report via update_state, and back-fill them into state with
decided_by="system".

The Worker is asked to call update_state(kind="commit"|"file_touched") but this
is discretionary. In the 2026-05-24 batch, 2 of 4 successful Workers committed
real branch work without reporting it. Treating Worker self-report as the only
source of truth makes the Proxy fly blind on longer runs. Reconciliation runs
every iteration against `state.baseline_ref` so missing entries are appended
with system provenance, while Worker-reported entries keep proxy provenance.
"""

import subprocess
from pathlib import Path

from orchestrator.state import CommitEntry, FileTouched, State


def git_head(project_dir: Path) -> str | None:
    """Return current HEAD sha for project_dir, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _git_log(project_dir: Path, baseline_ref: str) -> list[tuple[str, str]]:
    """Return [(sha, subject)] for commits in baseline_ref..HEAD."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H%x09%s", f"{baseline_ref}..HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    entries: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition("\t")
        sha = sha.strip()
        if sha:
            entries.append((sha, subject.strip()))
    return entries


def _git_changed_files(project_dir: Path, baseline_ref: str) -> list[str]:
    """Return paths that differ between baseline_ref and HEAD (committed + unstaged)."""
    paths: set[str] = set()
    for diff_args in (
        ["git", "diff", "--name-only", f"{baseline_ref}..HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            result = subprocess.run(
                diff_args,
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            p = line.strip()
            if p:
                paths.add(p)
    return sorted(paths)


def _sha_already_known(sha: str, known: list[str]) -> bool:
    """True if `sha` matches any stored sha by prefix in either direction.

    The Worker often self-reports a short sha (e.g. `6eae5f8`) via update_state,
    while `git log` returns full 40-char shas. A naive equality check
    double-counts the same commit. Treat one as known if it's a prefix of the
    other or vice versa, minimum 7 chars (git's default short-sha length).
    """
    if len(sha) < 7:
        return False
    for k in known:
        if len(k) < 7:
            continue
        if sha.startswith(k) or k.startswith(sha):
            return True
    return False


def reconcile(state: State, project_dir: Path) -> tuple[int, int]:
    """Append any commits / files visible in git that aren't already in state.

    Returns (commits_added, files_added). Worker-reported entries stay; new
    ones get decided_by="system". No-op if state.baseline_ref is None.
    """
    if state.baseline_ref is None:
        return 0, 0

    known_shas = [c.sha for c in state.commits]
    known_paths = {f.path for f in state.files_touched}
    commits_added = 0
    files_added = 0

    for sha, message in _git_log(project_dir, state.baseline_ref):
        if not _sha_already_known(sha, known_shas):
            state.commits.append(CommitEntry(sha=sha, message=message, decided_by="system"))
            known_shas.append(sha)
            commits_added += 1

    for path in _git_changed_files(project_dir, state.baseline_ref):
        if path not in known_paths:
            state.files_touched.append(FileTouched(path=path, decided_by="system"))
            known_paths.add(path)
            files_added += 1

    return commits_added, files_added
