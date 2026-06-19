"""Cheap reward-hacking tripwire for the verify gate (Wave 0 reliability core).

verify.py runs the goal's own command in the Worker's tree, so a green build is
only trustworthy if the tests themselves were not weakened to make the red go
away. Before the gate blesses a pass as `completed`, this scans the test files
that changed since `baseline_ref` and trips on the strong fingerprint of a gamed
gate: a test file DELETED, or its assertion / test-case count DROPPED versus the
baseline blob.

This is the CHEAP tripwire, not the full held-out verifier (Wave 2). It cannot
catch every weakening (a Worker can keep the assertion count and invert the
logic), only the blatant "delete the failing test" and "gut the assertions"
moves. The contract:

- STRONG signal (deleted test / dropped assertion count) -> the caller downgrades
  a verify pass to `escalate` and records the paths on State.tamper_paths so both
  proxies see them as ground truth.
- A test file merely edited (assertions added or unchanged) is a LOG signal only.
  Legit work edits tests constantly, so path-touched must never by itself fail
  the gate: that would be a false-positive storm.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# Path heuristics for "this is a test file", covering the JS/TS and Python repos
# the orchestrator drives. Domain-agnostic: a path-only match, no parsing.
_TEST_PATH_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)__tests__/"),
    re.compile(r"(^|/)spec/"),
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"_test\.py$"),
    re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$"),
    re.compile(r"_spec\.rb$"),
    re.compile(r"_test\.go$"),
)

# Call-like assertion / test-case markers. Anchored to a paren or keyword form so
# the count tracks real assertions and cases, not the words "test"/"should" in
# prose or comments. A net DROP in this count across an edit is the suspicious
# signal; the raw value is noisy but its direction is meaningful.
_ASSERTION_MARKERS = re.compile(
    r"""
      \bexpect\s*\(            # JS/Jest expect(
    | \bassert\b              # python assert, assert macros
    | \bit\s*\(               # mocha / jest it(
    | \btest\s*\(             # jest test(
    | \bdescribe\s*\(         # suite
    | \.to[A-Z]\w*\s*\(       # .toBe( .toEqual( .toThrow(
    | \bassert[A-Z]\w*\s*\(   # assertEqual( assertTrue(
    | \bself\.assert\w*\s*\(  # unittest self.assertX(
    """,
    re.VERBOSE,
)


def is_test_path(path: str) -> bool:
    return any(p.search(path) for p in _TEST_PATH_PATTERNS)


def count_assertions(text: str) -> int:
    return len(_ASSERTION_MARKERS.findall(text))


@dataclass
class TamperReport:
    # test files deleted or with a dropped assertion count vs baseline
    strong_paths: list[str] = field(default_factory=list)
    # test files merely edited (assertions same or added) - log only
    log_paths: list[str] = field(default_factory=list)
    # human-readable per-path notes for run.log and the escalation reason
    details: list[str] = field(default_factory=list)

    @property
    def tripped(self) -> bool:
        return bool(self.strong_paths)


def _git_show(project_dir: Path, ref: str, path: str) -> str | None:
    """Return the blob of `path` at `ref`, or None if it did not exist there."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def scan_tamper(
    project_dir: Path,
    baseline_ref: str | None,
    changed_paths: list[str],
) -> TamperReport:
    """Compare each changed TEST file against its baseline blob and classify.

    `changed_paths` is the reconciled set of paths git sees as changed since
    baseline (committed + working tree), e.g. ``[f.path for f in
    state.files_touched]``. No baseline (non-git project) is a no-op. The current
    content is read from the working tree, which is exactly what the verify
    command ran against.
    """
    report = TamperReport()
    if baseline_ref is None:
        return report

    for path in sorted(set(changed_paths)):
        if not is_test_path(path):
            continue
        baseline_blob = _git_show(project_dir, baseline_ref, path)
        if baseline_blob is None:
            # Newly added test file (absent at baseline): adding tests is good,
            # never tamper.
            continue
        baseline_count = count_assertions(baseline_blob)

        current_file = project_dir / path
        if not current_file.exists():
            report.strong_paths.append(path)
            report.details.append(
                f"{path}: test file deleted (had {baseline_count} assertions at baseline)"
            )
            continue

        try:
            current_text = current_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        current_count = count_assertions(current_text)

        if current_count < baseline_count:
            report.strong_paths.append(path)
            report.details.append(
                f"{path}: assertion count dropped {baseline_count} -> {current_count}"
            )
        else:
            report.log_paths.append(path)

    return report
