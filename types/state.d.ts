// GENERATED FILE: DO NOT EDIT BY HAND.
// Source: orchestrator/state.py (State.model_json_schema()).
// Regenerate with: uv run python scripts/gen_state_dts.py
//
// This typed contract mirrors the orchestrator State model so a consumer
// (e.g. a Kanban board reading state.json) cannot silently drift from the
// Python source. A drift test (tests/test_state_dts.py) fails the suite if
// this file is stale.

export type PlanStatus = "pending" | "in_progress" | "completed" | "skipped";
export type TaskStatus = "running" | "stopped" | "completed" | "escalated" | "failed";
export type DecidedBy = "proxy" | "user" | "system";
export type VerifyStatus = "pass" | "fail" | "misconfigured";

export interface AutonomyStats {
  decisions_between_escalations?: number;
  max_decisions_between_escalations?: number;
  autonomous_runtime_ms?: number;
  auto_approved?: number;
  auto_deferred?: number;
  escalated?: number;
}

export interface CommitEntry {
  sha: string;
  message?: string;
  decided_by?: DecidedBy;
  recorded_at?: string;
}

export interface Decision {
  turn: number;
  question: string;
  answer: string;
  reasoning: string;
  decided_by: DecidedBy;
}

export interface FileTouched {
  path: string;
  decided_by?: DecidedBy;
  recorded_at?: string;
}

export interface Handover {
  at_turn: number;
  reason: string;
  doc: string;
}

export interface HeldOutRecord {
  iteration: number;
  command: string;
  status: VerifyStatus;
  exit_code?: number | null;
  tail?: string;
  ran_at?: string;
}

export interface IterationUsage {
  iteration: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_creation_tokens?: number;
  model?: string;
  worker_ms?: number;
  proxy_ms?: number;
}

export interface PlanStep {
  id: number;
  step: string;
  status?: PlanStatus;
}

export interface ReconRecord {
  executor: string;
  model_id: string;
  elapsed_ms: number;
  ok?: boolean;
  ran_at?: string;
}

export interface VerifyRecord {
  iteration: number;
  command: string;
  status: VerifyStatus;
  exit_code?: number | null;
  tail?: string;
  ran_at?: string;
}

export interface State {
  task_id: string;
  started_at?: string;
  goal: string;
  plan?: PlanStep[];
  current_step_id?: number | null;
  decisions?: Decision[];
  files_touched?: FileTouched[];
  commits?: CommitEntry[];
  open_threads?: string[];
  iteration?: number;
  max_iterations?: number;
  handovers?: Handover[];
  usage?: IterationUsage[];
  estimated_cost_usd?: number;
  autonomy_stats?: AutonomyStats;
  baseline_ref?: string | null;
  repo_remote?: string | null;
  held_out_verify?: string | null;
  stakes_tier?: number | null;
  verify_attempts?: number;
  last_verify?: VerifyRecord | null;
  last_held_out?: HeldOutRecord | null;
  last_recon?: ReconRecord | null;
  stagnation_streak?: number;
  last_progress_key?: string | null;
  transient_retries?: number;
  tamper_paths?: string[];
  assumptions_made?: string[];
  plan_contradictions?: string[];
  confidence?: number | null;
  status?: TaskStatus;
  exit_reason?: string | null;
}
