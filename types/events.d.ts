// GENERATED FILE: DO NOT EDIT BY HAND.
// Source: orchestrator/events.py (Event.model_json_schema()).
// Regenerate with: uv run python scripts/gen_state_dts.py
//
// The normalized event-stream contract a Kanban board reads: the typed
// projection over State (orchestrator/events.py::project_events). A drift
// test (tests/test_state_dts.py) fails the suite if this file is stale.

export type EventType = "dispatched" | "iteration" | "decision" | "verify" | "held_out" | "tamper" | "stagnation" | "handover" | "escalation" | "terminal";

export interface Event {
  task_id: string;
  seq: number;
  iteration: number;
  ts: string;
  type: EventType;
  summary: string;
  data: { [key: string]: unknown };
}
