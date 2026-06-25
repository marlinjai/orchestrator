// GENERATED FILE: DO NOT EDIT BY HAND.
// Source: orchestrator/best_of.py (CohortResult.model_json_schema()).
// Regenerate with: uv run python scripts/gen_state_dts.py
//
// The best-of-N cohort contract a board reads: the typed record of an
// N-attempt cohort and its held-out-certified winner
// (orchestrator/best_of.py::run_best_of_n). A drift test
// (tests/test_state_dts.py) fails the suite if this file is stale.

export type TaskStatus = "running" | "stopped" | "completed" | "escalated" | "failed";
export type VerifyStatus = "pass" | "fail" | "misconfigured";

export interface CohortAttempt {
  attempt_index: number;
  task_id: string;
  branch: string;
  status: TaskStatus;
  held_out?: VerifyStatus | null;
  time_to_verified_ms?: number;
  selected?: boolean;
  exit_reason?: string | null;
}

export interface CohortResult {
  task_id: string;
  n: number;
  status: TaskStatus;
  selected_branch?: string | null;
  reason?: string;
  attempts?: CohortAttempt[];
  created_at?: string;
}
