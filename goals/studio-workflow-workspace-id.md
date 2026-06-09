---
task: studio-workflow-workspace-id
spec: src/lib/workflow/repository.ts
verify: pnpm test
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Make the held generation-workflow run infrastructure (the E2-infra slice, currently on this branch) merge-ready by (1) adding a forward-compat `workspaceId` column to the run models and (2) actually VERIFYING the executor against a real database for the first time (it was built and app-typechecks, but its `executor.spec.ts` has never run against a DB). This unblocks the run API and the future node canvas WITHOUT adopting Kysely/tenant-db yet (that is a deliberate later step, decision A1 / N15 lazy migration).

This branch already contains the workflow run infra. Your job is to finish it, not rebuild it.

## Read first (the existing E2-infra code on this branch)

- `prisma/schema.prisma`: the `WorkflowRun` + `WorkflowNodeRun` models + their enums (added by this slice).
- `prisma/migrations/20260608000000_workflow_runs/migration.sql`: the migration that creates them.
- `src/lib/workflow/repository.ts`: the persistence layer (Prisma queries for runs / node-runs). THIS is the file the workspace keying threads through.
- `src/lib/workflow/executor.ts` + `method-map.ts`: the pg-boss `run-workflow-node` executor (calls the repository; should not need workspace changes beyond passing it through).
- `src/lib/workflow/executor.spec.ts`: the executor test. It has NOT been verified against a real DB. Make it pass.
- `src/app/api/v1/workflows/run/route.ts` + `runs/[id]/route.ts`: the run API (creates a run, reads status).
- `src/test/global-setup.ts` + `vitest.config.ts`: how the test DB is set up (the verify gate uses this).
- The generation-workflow plan for context: `~/software-dev/knowledge-base/research/2026-06-08-generation-workflow-engine-plan.md`.

## Definition of done

1. **`workspaceId` column (forward-compat, Prisma, NOT Kysely):**
   - Add a non-null `workspaceId String` to `WorkflowRun` (the run is the tenancy envelope; `WorkflowNodeRun` inherits via its run, no separate column needed). Add an `@@index([workspaceId])`.
   - Studio has NO workspace model or auth-brain gating yet, so default it to a single constant: define `DEFAULT_WORKSPACE_ID` (a fixed UUID) in a small shared module (e.g. `src/lib/workflow/constants.ts`), set it on run creation in `repository.ts`, and leave a clear `// TODO` that this single-default placeholder is replaced by the real auth-brain workspace + the later Kysely/tenant-db migration (N15).
   - Reads in `repository.ts` may optionally accept + filter by `workspaceId` for forward-compat, but a single-tenant default is fine for now.
   - Add the Prisma migration for the new column (a new timestamped migration dir, or extend the existing workflow_runs migration if it has not been applied to any real DB; prefer a NEW additive migration to be safe). The column needs a default so existing rows (if any) and the migration are clean.
2. **The executor is VERIFIED against the real test DB:** `pnpm test` (the infisical-wrapped vitest suite that runs against a real Postgres via `global-setup.ts`) is GREEN, including `executor.spec.ts`. If the spec was a placeholder or fails against a real DB, make it a real, passing test that exercises a single-node run and a linear-chain run through the actual repository + executor. This is the core value of the slice.
3. The run API routes still typecheck and are covered or smoke-exercised.
4. Single conventional-commit on this branch with a message describing the workspace_id addition + the first real executor verification.

## Constraints

- Do NOT introduce Kysely or `@marlinjai/tenant-db` here. The persistence stays on Prisma. The Kysely/tenant-db conversion is a deliberate LATER slice (do not pre-empt it). Adding `workspaceId` to the Prisma model is the entire forward-compat step.
- Do NOT change the workflow DAG schema / registry (E1, `@marlinjai/studio-core/workflow`) or the E2-core runtime logic. Those are merged and frozen; you consume them.
- Do NOT touch `package.json` deps (no SDK or dependency bumps).
- Stay in this worktree. Do not push to any remote. When done, output a final completion message.

## Notes

- If `pnpm test` cannot reach Infisical or the test Postgres in the worktree, file an `open_thread` describing exactly what is unreachable and stop, rather than stubbing the DB out: a passing-without-a-real-DB test would defeat the entire point of this slice.
- Keep the change minimal and additive. The win is: workspace_id column + a genuinely DB-verified executor, so the slice can merge.
