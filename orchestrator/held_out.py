"""Held-out verifier gate (Wave 2 trust boundary).

The in-tree verify gate runs the goal's own command in the Worker's tree, so a
green build is only as trustworthy as the tests in that tree. The held-out gate
runs a SECOND, operator-sourced test set that lives on a path the Worker could
not write (the registry's ``held_out_verify``, resolved from the repo's real git
remote, see repo_registry.py). It runs only AFTER the in-tree verify passes and
the tamper tripwire clears: if the in-tree suite is green but the held-out suite
is red, the green was not earned. That is the reward-hack fingerprint, and it is
the strongest ground-truth signal the orchestrator has.

A held-out FAIL never feeds the Worker a retry: letting the Worker iterate
against the hidden tests would just teach to the held-out set and defeat the
point. Fail -> escalate, full stop. The orchestrator guarantees the command is
operator-authored (registry, not goal file) and runs it; the filesystem
isolation (held-out tests on a path the Worker's user cannot modify) is the
operator's setup, documented in docs/repos.example.toml.

Execution reuses verify.run_verify (same shell-command + exit-code machinery and
the same bash denylist), so this module is only the pure pass/fail -> gate
decision.
"""

from dataclasses import dataclass
from typing import Literal

from orchestrator.verify import VerifyOutcome


HeldOutAction = Literal["complete", "escalate"]


@dataclass
class HeldOutDecision:
    action: HeldOutAction
    exit_reason: str | None = None


def decide_after_held_out(
    outcome: VerifyOutcome, *, intree_verified: bool = True
) -> HeldOutDecision:
    """Pure decision from a held-out verify outcome. No I/O, no retry loop.

    - pass          -> complete. The visible green is corroborated by tests the
                       Worker could not touch.
    - fail          -> escalate. When an in-tree verify also passed this turn,
                       that is the reward-hack fingerprint (visible green, hidden
                       red); when the held-out gate ran as the sole gate, it just
                       means the build is not trustworthy. Never a Worker retry.
    - misconfigured -> escalate. A denylisted command, a timeout, or a process
                       that could not start: no clean signal, a human decides.

    `intree_verified` says whether an in-tree verify command passed this turn, so
    the fingerprint claim is only made when there is a visible green to contradict.
    """
    if outcome.status == "pass":
        return HeldOutDecision(action="complete")
    if outcome.status == "fail":
        if intree_verified:
            reason = (
                "REWARD-HACK FINGERPRINT: in-tree verify passed but the held-out "
                f"verify FAILED (exit {outcome.exit_code}). The visible green was "
                f"not earned. Tail:\n{outcome.tail}"
            )
        else:
            reason = (
                f"held-out verify FAILED (exit {outcome.exit_code}); the build is "
                f"not trustworthy. Tail:\n{outcome.tail}"
            )
        return HeldOutDecision(action="escalate", exit_reason=reason)
    return HeldOutDecision(
        action="escalate",
        exit_reason=f"held-out verify misconfigured: {outcome.tail}",
    )
