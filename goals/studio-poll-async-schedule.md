---
task: studio-poll-async-schedule
shared_state: []
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Wire the dormant async-job poller so async media jobs (video, music, 3D) cannot strand in `running` forever when a provider webhook is missed and no canvas tab is polling. Today completion in prod runs entirely off provider webhooks plus the per-run canvas fallback poll; the standalone `pollAsyncJobs` (`src/lib/jobs/pollers/async.ts`) is built and unit-tested but NOTHING schedules it (its docstring says "Schedule from a cron / pg-boss schedule at ~10-15s cadence"). Schedule it so an unwatched async job still completes.

## Read first

- `src/lib/jobs/pollers/async.ts` (`pollAsyncJobs`, `ASYNC_KINDS`; the debounce via `Job.lastProviderPollAt`)
- `src/lib/jobs/worker.ts` (`startWorker`: it already registers all 10 kinds and runs `reconcileInterruptedJobs` on startup; this is the natural home for a recurring schedule)
- `src/lib/jobs/queue.ts` (the pg-boss v12 wrapper, `startQueue`/`getQueue`; check what scheduling primitives pg-boss v12 exposes: `schedule`/`work` cron, or `sendAfter`)
- `src/lib/jobs/reconcile.ts` (the startup reconcile, as the pattern for a singleton job step)
- `src/lib/jobs/handlers/complete-job.ts` (the idempotent `completeJobFromTaskId` already-terminal guard, so a poll racing a webhook is safe)
- `src/app/api/v1/workflows/runs/[id]/route.ts` + `src/lib/workflow/run-fallback-poll.ts` (the existing on-demand nudge, for the debounce pattern and cadence)

## Definition of done

1. Add a recurring scheduled tick that calls `pollAsyncJobs` at a ~10-15s cadence, owned by the worker process (`startWorker`). Prefer pg-boss's own scheduling if v12 supports a sub-minute schedule cleanly; otherwise a guarded `setInterval` singleton in the worker process (cleared on shutdown) is acceptable. Pick the one that fits pg-boss v12; do not add a new dependency.
2. Idempotency + no thundering herd: `pollAsyncJobs` already debounces per job via `lastProviderPollAt`; ensure the schedule does not double-register across worker restarts (guard with a module-level flag or pg-boss's single-instance schedule semantics). Document the single-worker assumption (same caveat `reconcile.ts` carries): this tick assumes one worker process; a multi-instance deploy would need a leader lease.
3. The tick must be resilient: a poll error for one job is logged and does not crash the worker or block other jobs.
4. Test: a job in `running` past the debounce window gets polled by the scheduled path and, on a terminal upstream status, completes via `completeJobFromTaskId` (mock the provider poll + the completer). Assert the debounce skips a just-polled job.

Plus, always:
- the `verify` gate passes
- single conventional commit describing the WHY (unwatched async jobs could strand; now polled on a schedule)

## Constraints

- Do NOT change the completion logic (`completeJobFromTaskId`) or the webhook path.
- Do NOT re-enqueue or re-submit async jobs (that would double-spend real provider money); the poller only CHECKS upstream status and completes terminal ones. This mirrors why PR #68 only re-enqueues SYNC orphans.
- Keep the cadence configurable via an env var with a sane default (e.g. `ASYNC_POLL_INTERVAL_MS` default 12000) referenced through the existing env pattern.
- No em-dashes or en-dashes in new code/comments.
- Stay in this worktree. Do not push or merge.
- When done, output a final message that the task is complete.
