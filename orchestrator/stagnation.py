"""Stagnation / loop detection (Wave 0 reliability core).

The iteration cap is a runaway backstop, not a progress signal: a Worker can
burn the full cap thrashing on a failing verify gate or looping in clarification
without ever advancing. This module computes a cheap, hard-to-game progress
fingerprint each iteration and trips when it stays unchanged for N consecutive
iterations.

Design choices (see knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md):

- Progress = advancing the PLAN (current_step_id, completed steps), recording a
  DECISION, or moving the VERIFY outcome. Trivial commits / file edits are
  deliberately NOT counted as progress: a Worker making a no-op commit each
  iteration must not be able to dodge the detector (the dominant gaming move).
- On a trip the orchestrator hard-stops and fires the existing terminal-state
  notify (a cheap Telegram / macOS ping), NOT a fresh Marlin-Proxy LLM turn: the
  thrashing Worker must not influence the judgment that ends its loop, and
  re-deciding every iteration would amplify rate-limit and spend.
"""

import hashlib

from orchestrator.state import State

DEFAULT_STAGNATION_STREAK_CAP = 3


def progress_key(state: State) -> str:
    """Fingerprint of genuine forward progress for the current iteration.

    Intentionally excludes commit / file churn (gameable by no-op commits) and
    monotonic counters (iteration, usage, cost). Two iterations sharing a key
    made no structured progress between them.
    """
    completed_steps = sum(1 for s in state.plan if s.status == "completed")
    verify = state.last_verify
    parts = [
        str(state.current_step_id),
        str(completed_steps),
        str(len(state.decisions)),
        verify.status if verify else "none",
        str(verify.exit_code) if verify else "none",
        hashlib.sha256((verify.tail if verify else "").encode()).hexdigest()[:12],
    ]
    return "|".join(parts)


def update_stagnation(state: State) -> int:
    """Recompute the progress fingerprint and update the streak in place.

    Increments ``state.stagnation_streak`` when this iteration's key matches the
    previous one (no progress), resets it to 0 otherwise. Returns the new streak.
    The first observation always returns 0 (it only establishes the baseline).
    """
    key = progress_key(state)
    if state.last_progress_key is not None and key == state.last_progress_key:
        state.stagnation_streak += 1
    else:
        state.stagnation_streak = 0
    state.last_progress_key = key
    return state.stagnation_streak


def stagnation_hit(streak: int, cap: int = DEFAULT_STAGNATION_STREAK_CAP) -> bool:
    """True when the no-progress streak has reached the cap (cap <= 0 disables)."""
    if cap <= 0:
        return False
    return streak >= cap
