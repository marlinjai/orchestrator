"""Normalized event stream over the typed State contract.

PURE PROJECTION: this module reads a frozen `State` and emits an ordered,
normalized, typed feed of `Event`s. It writes nothing, mutates nothing, and is
not part of the control loop. A future Kanban board (and the `orchestrator
events` CLI) consume this feed instead of re-deriving meaning from the raw
state.json on every read.

`project_events(state)` is DETERMINISTIC, pure, and total: the same State
always yields the same ordered list, and every State (running, escalated,
stalled, or stakes-gated before any iteration) projects without raising.

Provenance is preserved, never flattened. The machine ground-truth signals
(dispatch metadata, verify / held-out / tamper / stagnation, all
orchestrator-run) carry `decided_by: "system"` in their payload, and each
`decision` event keeps its own `decided_by` verbatim so the board can show
what the orchestrator PROVED versus what the Worker merely SELF-REPORTED. The
trust model depends on that distinction surviving the projection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Literal

from pydantic import BaseModel

from orchestrator.state import State

# The fixed event vocabulary, in canonical (board) order. The `EventType`
# Literal below MUST mirror this tuple; the assert guards against drift. The
# codegen (scripts/gen_state_dts.py) imports `EVENT_TYPES` to emit the
# `EventType` alias, so this tuple is the single source of truth for the typed
# contract as well as the within-iteration tie-break order.
EVENT_TYPES: tuple[str, ...] = (
    "dispatched",
    "iteration",
    "decision",
    "verify",
    "held_out",
    "tamper",
    "stagnation",
    "handover",
    "escalation",
    "terminal",
)

EventType = Literal[
    "dispatched",
    "iteration",
    "decision",
    "verify",
    "held_out",
    "tamper",
    "stagnation",
    "handover",
    "escalation",
    "terminal",
]

# Fixed within-iteration ordering: events sharing an `iteration` break ties by
# this kind order (e.g. a verify and a held_out on the same iteration always
# emit verify-then-held_out, mirroring the real gate order).
_KIND_ORDER: dict[str, int] = {name: i for i, name in enumerate(EVENT_TYPES)}

# Defensive: the Literal and the tuple must stay in lockstep.
assert set(_KIND_ORDER) == set(EVENT_TYPES)


class Event(BaseModel):
    """One normalized, flat record in a task's event stream.

    Flat by design (not a deep discriminated union): the board reads a uniform
    row shape and drills into `data` for kind-specific fields. `seq` is the
    event's 0-based position within this task's ordered stream; `iteration` is
    the loop iteration it belongs to (0 = dispatch / pre-loop). `ts` is the
    best available timestamp (the record's own when it has one, else the run's
    start), so the cross-task `--all` merge stays time-ordered.
    """

    task_id: str
    seq: int
    iteration: int
    ts: datetime
    type: EventType
    summary: str
    data: dict


def _clip(text: str, limit: int = 120) -> str:
    """One-line, length-bounded summary text (no newlines, ASCII ellipsis)."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3] + "..."


def _latest_ts(state: State) -> datetime:
    """The latest timestamp we can attribute to a closing event.

    Verify / held-out carry real run timestamps; everything else falls back to
    the run start. Closing events (escalation, terminal) use the latest of
    these so they never sort before the gate that triggered them in `--all`.
    """
    candidates = [state.started_at]
    if state.last_verify is not None:
        candidates.append(state.last_verify.ran_at)
    if state.last_held_out is not None:
        candidates.append(state.last_held_out.ran_at)
    return max(candidates)


def project_events(state: State) -> list[Event]:
    """Project a State into its ordered, normalized event stream.

    Pure, deterministic, and total. Ordered by `iteration` then the fixed kind
    order; `seq` is assigned after ordering. Surfaces the board-critical
    signals: the held-out reward-hack fingerprint, tamper paths, stagnation,
    and the terminal status + exit_reason.
    """
    # Each item: a partial Event (everything but task_id + seq). Built in a
    # deterministic source order so the stable sort below is fully reproducible.
    items: list[dict] = []

    def add(iteration: int, type_: str, ts: datetime, summary: str, data: dict) -> None:
        items.append(
            {"iteration": iteration, "type": type_, "ts": ts, "summary": summary,
             "data": data}
        )

    # 1. dispatched: the run start + the operator-owned trust anchor (repo
    #    remote, stakes tier, held-out configured). All machine-resolved.
    add(
        0,
        "dispatched",
        state.started_at,
        f"dispatched: {_clip(state.goal)}",
        {
            "goal": state.goal,
            "repo_remote": state.repo_remote,
            "held_out_configured": state.held_out_verify is not None,
            "stakes_tier": state.stakes_tier,
            "max_iterations": state.max_iterations,
            "decided_by": "system",
        },
    )

    # 2. iteration heartbeats: one per recorded IterationUsage.
    for u in state.usage:
        model_suffix = f", model {u.model}" if u.model else ""
        add(
            u.iteration,
            "iteration",
            state.started_at,
            f"iteration {u.iteration}: {u.input_tokens + u.output_tokens} tokens"
            + model_suffix,
            {
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read_tokens": u.cache_read_tokens,
                "cache_creation_tokens": u.cache_creation_tokens,
                "model": u.model,
                "worker_ms": u.worker_ms,
                "proxy_ms": u.proxy_ms,
            },
        )

    # 3. decisions: PROVENANCE-FAITHFUL. `decided_by` is preserved verbatim so
    #    the board distinguishes system ground truth from Worker self-report.
    for d in state.decisions:
        add(
            d.turn,
            "decision",
            state.started_at,
            f"decision[{d.decided_by}]: {_clip(d.question)} -> {_clip(d.answer)}",
            {
                "question": d.question,
                "answer": d.answer,
                "reasoning": d.reasoning,
                "decided_by": d.decided_by,
            },
        )

    # 4. verify gate (orchestrator-run = system ground truth).
    if state.last_verify is not None:
        v = state.last_verify
        add(
            v.iteration,
            "verify",
            v.ran_at,
            f"verify {v.status} (exit {v.exit_code})",
            {
                "command": v.command,
                "status": v.status,
                "exit_code": v.exit_code,
                "tail": v.tail,
                "decided_by": "system",
            },
        )

    # 5. held-out gate: in-tree green + held-out red is THE reward-hack
    #    fingerprint. System ground truth; the flag is surfaced explicitly.
    if state.last_held_out is not None:
        h = state.last_held_out
        in_tree_green = state.last_verify is not None and state.last_verify.status == "pass"
        fingerprint = h.status == "fail" and in_tree_green
        if fingerprint:
            summary = (
                f"held-out FAIL (exit {h.exit_code}): REWARD-HACK FINGERPRINT, "
                "in-tree verify passed but the out-of-reach tests did not"
            )
        else:
            summary = f"held-out {h.status} (exit {h.exit_code})"
        add(
            h.iteration,
            "held_out",
            h.ran_at,
            summary,
            {
                "command": h.command,
                "status": h.status,
                "exit_code": h.exit_code,
                "tail": h.tail,
                "reward_hack_fingerprint": fingerprint,
                "decided_by": "system",
            },
        )

    # 6. tamper tripwire: test files weakened vs baseline (system ground truth).
    if state.tamper_paths:
        tamper_iter = state.last_verify.iteration if state.last_verify else state.iteration
        tamper_ts = state.last_verify.ran_at if state.last_verify else state.started_at
        add(
            tamper_iter,
            "tamper",
            tamper_ts,
            f"tamper tripwire: {len(state.tamper_paths)} test file(s) weakened "
            "vs baseline",
            {"paths": list(state.tamper_paths), "decided_by": "system"},
        )

    # 7. stagnation: structured-progress stall (system ground truth).
    if state.stagnation_streak > 0:
        add(
            state.iteration,
            "stagnation",
            state.started_at,
            f"stagnation streak: {state.stagnation_streak}",
            {"streak": state.stagnation_streak, "decided_by": "system"},
        )

    # 8. handovers: each context-window leg.
    for ho in state.handovers:
        add(
            ho.at_turn,
            "handover",
            state.started_at,
            f"handover at turn {ho.at_turn}: {_clip(ho.reason)}",
            {"at_turn": ho.at_turn, "reason": ho.reason, "doc": ho.doc},
        )

    # Anchor the closing events at (or past) the highest iteration seen so they
    # always sort last regardless of input shape (keeps the projection total).
    max_iter = state.iteration
    for it in items:
        if it["iteration"] > max_iter:
            max_iter = it["iteration"]

    # 9. escalation: the distinct "needs a human" signal (system-determined).
    if state.status == "escalated":
        add(
            max_iter,
            "escalation",
            _latest_ts(state),
            f"escalated: {_clip(state.exit_reason or 'reason unspecified')}",
            {"exit_reason": state.exit_reason, "decided_by": "system"},
        )

    # 10. terminal: lifecycle close for any non-running status.
    if state.status != "running":
        add(
            max_iter,
            "terminal",
            _latest_ts(state),
            f"{state.status}: {_clip(state.exit_reason or 'no reason recorded')}",
            {
                "status": state.status,
                "exit_reason": state.exit_reason,
                "decided_by": "system",
            },
        )

    # Stable sort by (iteration, kind order); ties keep the build order above.
    items.sort(key=lambda it: (it["iteration"], _KIND_ORDER[it["type"]]))
    return [Event(task_id=state.task_id, seq=i, **it) for i, it in enumerate(items)]


def merge_events(events: Iterable[Event]) -> list[Event]:
    """Merge per-task streams into one deterministic, time-ordered feed.

    Sorts by (ts, task_id, seq). `seq` is NOT renumbered: it stays the per-task
    ordinal so a board can still locate an event within its own task stream.
    """
    return sorted(events, key=lambda e: (e.ts, e.task_id, e.seq))


def _ensure_aware(dt: datetime) -> datetime:
    """Normalize a possibly-naive datetime to tz-aware UTC for comparison."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def filter_since(events: Iterable[Event], since: datetime) -> list[Event]:
    """Keep events whose `ts` is at or after `since` (tz-safe comparison)."""
    cutoff = _ensure_aware(since)
    return [e for e in events if _ensure_aware(e.ts) >= cutoff]
