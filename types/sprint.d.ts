// GENERATED FILE: DO NOT EDIT BY HAND.
// Source: orchestrator/sprint.py (SprintRecord.model_json_schema()).
// Regenerate with: uv run python scripts/gen_state_dts.py
//
// The sprint contract a board reads (sprint.json next to a sprint's
// state.json): the slices, their status and the final held-out result

export type TaskStatus = "running" | "stopped" | "completed" | "escalated" | "failed";
export type VerifyStatus = "pass" | "fail" | "misconfigured";

export interface HeldOutRecord {
  iteration: number;
  command: string;
  status: VerifyStatus;
  exit_code?: number | null;
  tail?: string;
  ran_at?: string;
}

export interface SlicePlan {
  title: string;
  spec: string;
  files: string[];
  tests: string[];
}

export interface SliceRecord {
  index: number;
  plan: SlicePlan;
  status?: "pending" | "running" | "completed" | "escalated" | "stopped" | "failed";
  attempts?: number;
  task_id?: string | null;
  exit_reason?: string | null;
  commits?: string[];
  handover_path?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface SprintRecord {
  task_id: string;
  status?: TaskStatus;
  reason?: string;
  branch?: string | null;
  worktree?: string | null;
  handover_dir?: string | null;
  slices?: SliceRecord[];
  held_out?: HeldOutRecord | null;
  created_at?: string;
  updated_at?: string;
}
