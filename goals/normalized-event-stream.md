---
task: normalized-event-stream
verify: uv run pytest -q && uv run ruff check orchestrator/ tests/
# Target repo (--project): ~/software-dev/orchestrator  (the orchestrator's OWN repo: high-stakes)
# Wave 2 / leaf L7 -- the board's data layer. Decision source:
#   knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (sections 5 Wave 2, 7 control-plane layering)
#   docs/handovers/2026-06-20-roadmap-driver-handover.md (L7: normalized event stream over the typed state contract)
# depends_on: [state-dts-typed-contract]  (MERGED to master)
shared_state: [state-schema]
---

# Goal

Build the **normalized event stream**: the board's data layer over the typed `State` contract (L3).
The orchestrator already records everything a run does in `state.json` (decisions, per-iteration usage,
verify, held-out, tamper, stagnation, handovers, terminal state). This leaf turns that per-task record
into an ORDERED, NORMALIZED, TYPED feed of events that the future Wave-3 Kanban board reads, plus a
read-only CLI to emit it. It is a pure PROJECTION over existing state: it changes NOTHING in the control
loop, adds no new write path, and never mutates `State`.

## Read first

- `orchestrator/state.py`: the full `State` model + nested models (the source the projection reads:
  `decisions`, `usage`, `last_verify`, `last_held_out`, `tamper_paths`, `handovers`, `stagnation_streak`,
  `status`, `exit_reason`, `started_at`, `iteration`, `repo_remote`, `held_out_verify`, `stakes_tier`).
- `scripts/gen_state_dts.py` + `types/state.d.ts` + `tests/test_state_dts.py` (L3): the codegen pattern this leaf EXTENDS for the event types. Do not fork it; add to it.
- `orchestrator/cli.py` (or wherever subcommands register: `status`, `logs`, `stop`, `start`, `marlin-proxy`): mirror that pattern for the new `events` subcommand.
- `orchestrator/state.py` load helpers + `~/.orchestrator/tasks/<id>/state.json` layout (how a State is read back).

## Scope

1. **`orchestrator/events.py`** (new): a pydantic `Event` model -- a FLAT normalized record (keep it flat,
   not a deep discriminated union, so the board + the codegen stay simple):
   `task_id: str`, `seq: int` (stable ordinal within the task), `iteration: int`, `ts: datetime`,
   `type: EventType` (a `Literal` union), `summary: str`, `data: dict[str, ...]` (a small typed-ish
   payload). `EventType` covers the real state movements: `dispatched`, `iteration`, `decision`,
   `verify`, `held_out`, `tamper`, `stagnation`, `handover`, `escalation`, `terminal`.
2. **`project_events(state: State) -> list[Event]`** (in `events.py`): a DETERMINISTIC pure function that
   projects one `State` into its ordered event list (ordered by iteration, then a fixed kind order).
   It must surface the board-critical signals the roadmap names: held-out pass/fail (the reward-hack
   fingerprint), tamper paths, stagnation, and the terminal status + exit_reason. Provenance-faithful:
   a `decided_by=system` reconcile and a self-reported decision are distinguishable in the payload.
3. **`orchestrator events` CLI subcommand** (read-only): `orchestrator events --task-id <id>` emits that
   task's normalized stream as JSONL on stdout; `orchestrator events --all [--since <ISO>]` emits the
   merged, time-ordered stream across every `~/.orchestrator/tasks/*/state.json`. Pure read: it loads
   state, projects, prints. Never writes, never touches the loop.
4. **Typed contract for events**: EXTEND `scripts/gen_state_dts.py` to also emit the `Event` + `EventType`
   types (either appended into `types/state.d.ts` or a sibling `types/events.d.ts` -- your call, but it
   MUST be generated, not hand-written, and covered by the freshness test so the board can never drift).
5. **Tests** (`tests/test_events.py` + extend the dts freshness test): a `State` carrying decisions +
   a failing held-out + tamper paths + a terminal escalation projects the EXACT expected ordered events
   (assert types, order, and that held-out-fail / tamper / stagnation are present); the `events` CLI emits
   valid JSONL for `--task-id` and merges+orders for `--all`; the events contract regenerates idempotently
   and the freshness test reddens on an `Event` change (prove-then-revert).

## Definition of done

- `orchestrator/events.py` with `Event`, `EventType`, and `project_events` (pure, deterministic, total).
- `orchestrator events --task-id <id>` and `--all [--since]` emit correct normalized JSONL; read-only.
- The event types are GENERATED into the dts contract and freshness-tested (drift reddens `uv run pytest`).
- `uv run pytest -q` green (add the new tests); `uv run ruff check orchestrator/ tests/` clean.
- NOTHING in the control loop (`orchestrator.py`, `worker.py`, `proxy.py`) changed: prove the projection is a pure read by leaving those files untouched.
- ROADMAP.md "Shipped" updated (existing format, compact, no new columns).
- One conventional commit on the worktree branch.

## Constraints

- PURE PROJECTION. No new write path, no mutation of `State`, no change to the control loop or its outputs. The board reads; the orchestrator keeps writing exactly `state.json` as today.
- No new third-party dependency; reuse pydantic + the L3 codegen approach. No node toolchain.
- Faithful to provenance: do not flatten `decided_by=system` vs self-reported into the same thing; the board must be able to show machine-ground-truth vs Worker-self-report (the trust model).
- Do NOT build the board itself, an HTTP server, websockets, or a DB. This is the FEED (a CLI + a typed projection); L9 consumes it. Stay in scope.
- No em-dashes / en-dashes. Conventional-commit message. Stay in the worktree; do not push.

## Notes

- This is the cheap, high-leverage data layer: the board (L9) becomes "render this JSONL stream + link to the authenticated approve action," because the hard part (a normalized, typed, provenance-faithful event feed) lives here.
- Keep `Event.data` modest and serializable (the board renders it). Do not dump the whole transcript; surface the decision text, verify tail, held-out status, tamper paths, exit_reason.
