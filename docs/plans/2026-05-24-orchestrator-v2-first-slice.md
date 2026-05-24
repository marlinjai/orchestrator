---
type: plan
status: decided
date: 2026-05-24
title: Orchestrator v2 first slice, state reconciliation + token telemetry
tags: [orchestrator, v2, state, telemetry]
summary: Close the trust gap where Worker-reported state silently underreports commits and files, and capture per-iteration token usage so multi-iteration runs have observability before they happen. One PR, one evening, no Proxy or CLI verb changes.
---

# Orchestrator v2 first slice: state reconciliation + token telemetry

## Why

Two structural gaps surfaced in the 2026-05-24 dogfood batch:

1. **State lies about commits.** 2 of 4 successful Workers committed real branch work but never called `update_state(kind="commit")`. Their `state.json` showed `commits: []` while git history showed valid commits. The Proxy makes decisions from state; silent under-reporting means the Proxy is flying blind on longer runs, and downstream tooling (status output, future scoring, future loop detection) trusts a lie. The v0.1.0 dogfood already flagged the same pattern for `decision` kind. Worker prompt nudging is not enough, discretionary reporting is structurally unreliable.

2. **No token visibility.** Every field report flags this. All runs to date have been single-iteration low-token tasks. We have zero data on burn rate, rate-limit headroom, or when handover should fire. The first multi-iteration task on Pro will hit limits with no warning surface and no postmortem data.

Both gaps unblock downstream v2 themes (loop detection, handover, Proxy feedback). Land them together because they share `state.py` schema work.

## What ships

One PR with these changes:

### `orchestrator/state.py`

Add provenance to commit and file entries; add per-iteration usage list.

- New model `CommitEntry(sha: str, message: str, decided_by: DecidedBy, recorded_at: datetime)`.
- New model `FileTouched(path: str, decided_by: DecidedBy, recorded_at: datetime)`.
- New model `IterationUsage(iteration: int, input_tokens: int, output_tokens: int, cache_read_tokens: int, cache_creation_tokens: int, model: str, wall_ms: int)`.
- Change `commits: list[str]` to `commits: list[CommitEntry]`.
- Change `files_touched: list[str]` to `files_touched: list[FileTouched]`.
- Add `usage: list[IterationUsage] = []`.
- Add `baseline_ref: str | None = None` (git rev of project HEAD at orchestrator start; needed for reconciliation).

Schema break is acceptable per dev-phase no-backcompat rule. Document that existing `state.json` files from prior runs will fail to load.

### `orchestrator/tools.py`

`update_state` MCP tool still accepts the same kinds, but commit and file entries get stamped `decided_by="proxy"` (i.e. "Worker self-reported, surfaced via Proxy state channel") rather than the old free-string format. Trivial code change.

### `orchestrator/orchestrator.py`

Three insertions in `run_orchestrator`:

1. **Baseline snapshot (before loop):** after `_initialize_state`, shell out `git rev-parse HEAD` in `cfg.project_dir`; persist as `state.baseline_ref`. If the project is not a git repo, leave None and skip reconciliation. Use `subprocess.run`, not a new dep.

2. **Per-iteration reconciliation (after Worker turn returns):** between line ~172 (chunks returned) and line ~175 (`state = load_state(state_path)`), run reconciliation:
   - `git log --format=%H %s baseline_ref..HEAD` for new commits.
   - `git diff --name-only baseline_ref HEAD` for changed files.
   - Append any commits not already in `state.commits` (matched by sha) with `decided_by="system"`.
   - Append any files not already in `state.files_touched` (matched by path) with `decided_by="system"`.
   - Save state.

3. **Telemetry capture (inside `_run_one_turn`):** the SDK emits `AssistantMessage.usage: dict | None` on assistant turns and a session-level usage on `ResultMessage`. Walk the stream and accumulate input/output/cache tokens for the iteration. At end of `_run_one_turn`, build one `IterationUsage` and append to `state.usage`. Wall-clock measured by `time.monotonic()` around the turn.

### `orchestrator/transcript.py`

Add `extract_usage(msg) -> dict | None` helper that mirrors `extract_text`. Returns `msg.usage` or `msg["message"]["usage"]` depending on the envelope shape. Empty dict if absent.

### `orchestrator/main.py`

`orchestrator status` output: print the new `usage` and `baseline_ref` fields in the rich table. Add a "tokens" summary row (sum of all iterations).

### Tests

- `test_state.py`: round-trip the new schema; assert old-shape state.json raises validation error.
- `test_transcript.py`: `extract_usage` cases for AssistantMessage shape (real shape) + dict envelope shape (legacy synthetic) + missing-usage case.
- `test_orchestrator.py`: with a fake git repo fixture, run a stub Worker turn that creates a commit without calling update_state, assert post-iteration state has the commit with `decided_by="system"`.
- New `test_reconcile.py` if reconciliation logic lives in its own module (recommended).

## What does NOT ship in this slice

- No persona changes (Proxy doesn't yet see `decided_by` distinction; that's Theme 6, later).
- No CLI verb changes (`orchestrator batch` is Theme 7, later).
- No automatic loop-detection threshold (Theme 4, later).
- No handover scaffold (Theme 5, later).
- No env-mode allow/deny-list generalization beyond the current `ANTHROPIC_API_KEY` scrub (Theme 3, later).
- No `usage` thresholds or warnings in Proxy context (telemetry is capture-only this slice).

## Decisions to record

1. **Reconciliation runs every iteration, not just at end.** Cheap (one `git log` + one `git diff`); means state stays accurate even if a run is killed mid-batch.
2. **`decided_by` provenance is on every commit/file entry, not just reconciliation ones.** Worker-reported entries get `decided_by="proxy"`; orchestrator-detected entries get `decided_by="system"`. Future direct human edits (via a yet-to-exist CLI) would be `decided_by="user"`.
3. **Schema break, no migration.** Per dev-phase no-backcompat rule. The four-state.json files from this session's batch get archived by hand; we move on.
4. **Telemetry is capture-only.** No alerting, no thresholds, no Proxy-side context. Land observability first, react second.

## Test plan

1. Unit tests pass (pytest, 91 + new).
2. Local re-run of the v0.1.0 dogfood goal (`goals/write-orchestrator-plan.md` if still applicable, or a smaller new one) and verify:
   - `state.json` has populated `usage` array.
   - `commits` and `files_touched` have provenance entries (likely a mix of `proxy` and `system` based on Worker discipline).
   - `orchestrator status` renders the new fields.
3. No regression on the parallel-batch recipe (still able to launch detached, monitor via state.json).

## Out of scope, deferred to next slice

- `orchestrator/docs/troubleshooting.md` with secrets/auth section (Stream 3 docs work).
- `~/.claude/skills/orchestrator-dispatch/SKILL.md` (Stream 2 distribution).
- `uv tool install` packaging hygiene (Stream 2 distribution).

## Open questions

- **`AssistantMessage.usage` shape.** Confirmed type signature is `dict[str, Any] | None`. The exact keys (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) need to be observed in a real session to lock down `IterationUsage` fields. Do this empirically in the implementation: print `msg.usage` on the first dogfood run and adjust the model fields if needed.
- **Wall-clock measurement.** Per-iteration wall time is `_run_one_turn` duration, which includes the Proxy call. Keep this conflation or split into `worker_ms` + `proxy_ms`? Recommend split for postmortem usefulness, marginal cost.

## Done criteria

- All tests green.
- One real dogfood run produces a state.json with populated `usage`, `commits[*].decided_by`, `files_touched[*].decided_by`, and `baseline_ref`.
- `orchestrator status` displays totals.
- Commit message: `feat(state): reconcile commits/files against git + capture per-iteration token usage`.
- Status of this plan flips to `completed`.

## Estimated effort

One focused evening session (~2 hours implementation, 1 hour test + dogfood verification).
