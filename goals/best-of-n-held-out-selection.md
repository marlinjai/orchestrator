---
task: best-of-n-held-out-selection
verify: uv run pytest -q && uv run ruff check orchestrator/ tests/
# Target repo (--project): ~/software-dev/orchestrator  (the orchestrator's OWN repo: high-stakes)
# Wave 2 / leaf L8. Decision source:
#   knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (Wave 3: "best-of-N", still gated on the held-out verifier; section 4 trust prereq)
#   docs/handovers/2026-06-20-roadmap-driver-handover.md (L8: cheap on subscription, GATED on the held-out verifier; selection certified by held-out-green, never a Worker-visible signal)
# depends_on: [orchestrator-executor-profile-mercury-recon]  (L4, MERGED) + held-out verifier (MERGED)
shared_state: [state-schema]
---

# Goal

Add **best-of-N**: run N independent Worker attempts on the same goal, then SELECT the winner using the
HELD-OUT verifier and ONLY the held-out verifier, never a Worker-visible signal. The whole point is that
selection cannot be reward-hacked: the in-tree verify is what the Worker sees and can game, so it can never
be the selection metric. This is a thin ORCHESTRATION LAYER over the existing single-attempt machinery
(`run_orchestrator` + worktree-per-attempt isolation + `held_out.py`); it is NOT a new execution engine and
NOT a change to the Worker/Proxy loop.

## Why this is allowed now (the gate)

best-of-N ships ONLY because the held-out verifier exists and is merged. Without a trustworthy out-of-reach
signal, "best of N" would just amplify the most convincing reward-hack. So this leaf MUST REFUSE to select
when no held-out is available for the repo: if the repo has no `held_out_verify` (registry) and no
`--held-out` override, best-of-N escalates rather than picking by the in-tree verify alone.

## Read first

- `orchestrator/orchestrator.py`: `run_orchestrator` (its config, the `--worktree` path, how a single attempt
  produces a terminal `State` with `status`, `last_verify`, `last_held_out`, `tamper_paths`, and the
  time-to-verified telemetry). The best-of-N layer CALLS this N times, each isolated.
- `orchestrator/held_out.py` + `repo_registry.py`: how the held-out command is resolved (registry by real
  remote, or `--held-out` override) and run; `state.last_held_out` (pass/fail/misconfigured). This is the
  ONLY selection signal.
- `orchestrator/worktree.py`: worktree-per-attempt isolation (each attempt needs its own tree/branch so N attempts never collide).
- `orchestrator/state.py` (+ the L3 `state.d.ts` codegen, and L7 `events.py` if merged by now): a best-of-N run needs a small typed record of the cohort (per-attempt branch, terminal status, held-out result, time_to_verified) for the board to render.
- `orchestrator/config.py` + the CLI registration: mirror the existing flag/subcommand pattern.

## Scope

1. **`orchestrator/best_of.py`** (new): `run_best_of_n(cfg, n)` that launches N attempts of the same goal,
   each via the existing single-attempt path in its OWN worktree/branch (`orchestrator/<task-id>-attempt-<k>`),
   reusing `worktree.py`. Attempts may run sequentially (simplest, safe) or with a small bounded concurrency;
   sequential is acceptable for the first slice (document the choice). Collect each attempt's terminal `State`.
2. **Held-out-certified selection** (the heart): from the cohort, consider ONLY attempts that reached
   `completed` AND whose held-out gate PASSED (`last_held_out.status == pass`). Among those, pick the winner by
   the lowest `time_to_verified_result` (tie-break deterministically, e.g. attempt index). If NO attempt is
   held-out-green: do NOT pick one; set the cohort result to `escalate` with a clear reason. NEVER select by
   `last_verify` (Worker-visible) alone, and never feed a held-out result back to a Worker as a retry.
3. **Hard gate**: if no held-out is resolvable for the repo (no registry `held_out_verify`, no `--held-out`),
   `run_best_of_n` REFUSES (escalates with "best-of-N requires a held-out verifier") and runs zero attempts, by design.
4. **CLI**: a `--best-of N` flag on `orchestrator start` (or an `orchestrator best-of` subcommand, your call;
   match the existing CLI shape). Composes with `--worktree`, `--held-out`, and the stakes gate (a tier-3+
   repo still needs `--confirm-stakes`; best-of-N does not relax it).
5. **Typed cohort record on State/result** for the board: per-attempt `{branch, status, held_out, time_to_verified_ms, selected: bool}`, and the cohort's selected branch (or the escalation). Extend the dts codegen + freshness test so the board has the typed shape.
6. **Tests** (`tests/test_best_of.py`): selection picks the held-out-green attempt with the lowest time_to_verified, NOT the one with the greenest in-tree verify; a cohort with zero held-out-green escalates (no selection); the no-held-out-configured case refuses before running any attempt; a held-out result is never fed back as a Worker retry. Mock the per-attempt runner so tests do not spawn real Workers.

## Definition of done

- `run_best_of_n` runs N isolated attempts and selects ONLY by held-out-green + lowest time_to_verified; zero held-out-green escalates; no-held-out-configured refuses up front.
- `--best-of N` wired; composes with `--worktree` / `--held-out` / the stakes gate.
- The cohort record is typed + generated into the dts contract + freshness-tested.
- `uv run pytest -q` green (the new selection + refusal + no-retry tests, all with mocked attempts); `uv run ruff check orchestrator/ tests/` clean.
- The single-attempt path is unchanged when `--best-of` is absent (prove: default behavior byte-for-byte).
- ROADMAP.md "Shipped" updated (existing format, compact). SKILL.md gains a short note: best-of-N requires a held-out verifier, selection is held-out-certified, never Worker-visible.
- One conventional commit on the worktree branch.

## Constraints

- Selection signal is the held-out verifier ONLY. The in-tree verify is Worker-visible and reward-hackable; it can gate `completed` per attempt but NEVER selects the winner.
- No held-out resolvable => refuse (escalate), run nothing. This is a safety property, not an edge case.
- A held-out fail is NEVER a Worker retry (that would teach to the hidden tests). It only removes that attempt from selection.
- Reuse `run_orchestrator` + `worktree.py` + `held_out.py`; do NOT fork the loop or write a second executor. Thin orchestration layer only.
- Each attempt fully isolated (own worktree/branch) so N attempts never collide.
- Stakes gate still applies (tier-3+ needs `--confirm-stakes`); best-of-N never relaxes it. Subscription billing (flat), so N attempts are cheap, but keep the per-run token cap honored per attempt.
- No em-dashes / en-dashes. Conventional-commit message. Stay in the worktree; do not push.

## Notes

- This is the prerequisite for the Wave-3 planner choosing "best-of-N" as an execution strategy (L10), but it does NOT implement the planner. It just makes held-out-certified best-of-N a thing the planner can request.
- Keep N modest by default (e.g. 3) and bounded; document that wall-clock is N attempts (sequential) so the operator sizes caps accordingly.
- If L7's `events.py` is merged, emit a cohort/selection event so the board can render the best-of-N race; if not yet merged, leave a clean seam (do not block on it).
