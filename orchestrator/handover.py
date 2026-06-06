"""Context handover support: prompt builder, git verifier, and fresh-session seed.

Called by orchestrator.py when input_tokens crosses context_handover_tokens.
The Worker is asked to write HANDOVER.md anchored to git-verified state, then
the orchestrator spawns a fresh ClaudeSDKClient seeded with that file.

Layer 3 property: "done" is defined by git commits and test results, not the
Worker's self-reported prose. verify_handover_doc cross-checks the VERIFIED
DONE section against reconcile output and flags any SHA that is not in git log.
"""

import re
import subprocess
from pathlib import Path

from orchestrator.state import State


_HANDOVER_COMPLETE_MARKER = "HANDOVER_COMPLETE"

HANDOVER_WORKER_PROMPT = """\
You are approaching context capacity. Before this session ends, write a file
called HANDOVER.md in the task root directory (the project you are working in,
not the orchestrator directory). Fill every section from what you can VERIFY
(git log, test output, file contents), not from memory.

## GOAL
(copy the original goal verbatim)

## VERIFIED DONE (git-confirmed only)
List only work that appears in `git log <baseline>..HEAD`. For each entry:
- SHA: <full commit sha>
- Files: <comma-separated changed files>
- Summary: <one-line description>
- Tests: passed | failing | untested

## IN FLIGHT (uncommitted)
Files you touched this iteration that are not yet committed. One per line:
- <path>: <current state: working | broken | partial>

## NEXT EXACT ACTION
The single concrete action the fresh session should take first. Be specific:
include the file, the function or line range, what to change and why. No
rediscovery needed.

## OPEN DECISIONS
Questions that need the Proxy before the fresh session can proceed.
One per line: "Q: <question>"

## GOTCHAS
Non-obvious constraints or failure modes you discovered. One per line.

After writing the file, respond with only: HANDOVER_COMPLETE
"""


def build_handover_prompt(state: State) -> str:
    """Build the message sent to the Worker to trigger HANDOVER.md authoring."""
    tokens = state.usage[-1].input_tokens if state.usage else 0
    leg = len(state.handovers) + 1
    header = (
        f"Context checkpoint: {tokens:,} input tokens consumed (leg {leg}). "
        "Write HANDOVER.md and reply HANDOVER_COMPLETE per the instructions below.\n\n"
    )
    return header + HANDOVER_WORKER_PROMPT


def is_handover_complete(worker_output: str) -> bool:
    return _HANDOVER_COMPLETE_MARKER in worker_output


def _git_log_shas(project_dir: Path, baseline_ref: str) -> set[str]:
    """Return the set of full SHAs in baseline_ref..HEAD."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H", f"{baseline_ref}..HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def verify_handover_doc(doc: str, state: State, project_dir: Path) -> list[str]:
    """Cross-check HANDOVER.md VERIFIED DONE section against actual git state.

    Returns a list of discrepancy strings. Empty list means clean.
    Each string is human-readable and included in the fresh-session seed warning.
    """
    if state.baseline_ref is None:
        return []

    real_shas = _git_log_shas(project_dir, state.baseline_ref)
    if not real_shas:
        return []

    discrepancies: list[str] = []

    # Extract all "SHA: <value>" lines from the doc
    sha_pattern = re.compile(r"^\s*-?\s*SHA:\s*([0-9a-f]{7,40})\s*$", re.MULTILINE | re.IGNORECASE)
    claimed_shas = sha_pattern.findall(doc)

    for claimed in claimed_shas:
        # Accept prefix match (Worker may use short shas)
        matched = any(real.startswith(claimed) or claimed.startswith(real) for real in real_shas)
        if not matched:
            discrepancies.append(
                f"SHA {claimed!r} in HANDOVER.md VERIFIED DONE not found in git log {state.baseline_ref}..HEAD"
            )

    # Check for real commits that are not mentioned at all
    state_shas = {c.sha for c in state.commits}
    for real_sha in real_shas:
        mentioned = any(
            real_sha.startswith(c) or c.startswith(real_sha)
            for c in (claimed_shas + list(state_shas))
        )
        if not mentioned:
            discrepancies.append(
                f"Commit {real_sha[:12]} is in git log but not mentioned in HANDOVER.md"
            )

    return discrepancies


def seed_fresh_session_message(
    doc_path: Path,
    state: State,
    discrepancies: list[str],
) -> str:
    """Build the first user message for the fresh session.

    Includes the full HANDOVER.md contents and any git-verification warnings.
    """
    leg = len(state.handovers)
    tokens = state.usage[-1].input_tokens if state.usage else 0

    doc_contents = doc_path.read_text() if doc_path.exists() else "(HANDOVER.md not found)"

    header = (
        f"[HANDOVER FROM PREVIOUS SESSION - leg {leg}, "
        f"turn {state.iteration}, input_tokens {tokens:,}]\n\n"
        "The previous session wrote the following checkpoint. "
        "Continue from NEXT EXACT ACTION.\n"
    )

    if discrepancies:
        warning = (
            "\n[WARNING: git reconciliation found discrepancies between HANDOVER.md "
            "and actual git state. Verify before trusting the VERIFIED DONE section.]\n"
        )
        for d in discrepancies:
            warning += f"  - {d}\n"
    else:
        warning = "\n[git reconciliation: no discrepancies found]\n"

    footer = (
        "\nCall update_state(\"commit\") after each commit. "
        "Call the Proxy if you need to resolve a question from OPEN DECISIONS before proceeding."
    )

    return header + warning + "\n---\n\n" + doc_contents + "\n---\n" + footer
