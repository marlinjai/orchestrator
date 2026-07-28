---
task: analytics-erasure-consumer
depends_on: [authbrain-era3-convergence]
verify: pnpm exec vitest run && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Analytics consumes auth-brain's signed GDPR erasure webhooks (erasure-plan follow-up; pre-launch gate item 7). Mirror of the Studio consumer (lumitra-studio `src/app/api/internal/erasure/` + `src/lib/erasure/`, merged in lumitra-studio#119; read it as the reference implementation), adapted to analytics' WORKSPACE-scoped data model.

## Precondition (run FIRST, abort loudly on failure)

`npm view @marlinjai/auth-brain-shared@1.4.0 version` must print `1.4.0` (it adds `workspace_ids` to the `tenant.erased` payload, which this consumer needs). If not, STOP and report.

## Read first

- The reference consumer: `/Users/marlinjai/software-dev/ERP-suite/projects/lumitra-studio/src/app/api/internal/erasure/route.ts` and `src/lib/erasure/` (signature verification, idempotency ledger, ack semantics)
- This repo's auth seams: `packages/dashboard/src/lib/auth-api.ts`, `auth-check.ts`, `src/middleware.ts` (the new route is signature-authed, exempt from session gates)
- Data model: `packages/dashboard/src/app/api/projects/route.ts` (projects keyed by auth-brain `workspace_id`), the Postgres schema for projects/experiments/flags/funnels, and the ClickHouse client + how events are keyed by `project_id`

## Definition of done

1. **`POST /api/internal/erasure`** in the dashboard app: HMAC-SHA256 over the raw body with env `ANALYTICS_ERASURE_WEBHOOK_SECRET` (constant-time, min-length, 401 fail-closed, 500 when env missing), same header convention as the Studio consumer (mirror it exactly), idempotency ledger table (replayed event_id -> 200 no-op), ack 2xx only after ALL deletion work; partial failure 5xx so auth-brain retries; deletions idempotent.
2. **`tenant.erased`**: using the payload's `workspace_ids: string[]` (shared 1.4.0), delete every analytics project whose `workspace_id` is in the list, plus ALL project-scoped data: Postgres (experiments, flags, funnels, sites/settings, whatever the schema hangs off a project) AND ClickHouse events for those project ids (async mutations are acceptable; issue them and verify submission). Other projects untouched (isolation assertion in tests).
3. **`user.erased`**: audit the schema for user-keyed rows (e.g. creator references, OAuth artifacts). Delete/anonymize what exists; if genuinely nothing, record + ack with the verified-no-op comment pattern from the Studio consumer.
4. **Tests**: signature valid/invalid/missing/env-missing; replay no-op; wire-contract against `@marlinjai/auth-brain-shared@1.4.0` payload schemas + the auth-brain signing convention; cascade fixture (two workspaces erased, one untouched) asserting Postgres rows gone, ClickHouse mutation issued per project, isolation preserved; partial-failure retry completes remaining work.
5. `pnpm exec vitest run && pnpm typecheck && pnpm lint` green at root. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push. Do not change analytics auth, project creation, or tracking ingestion.
- The secret is referenced by env NAME only (operator scaffolds the value server-side in both Infisical projects).
- Never log webhook bodies, secrets, or signatures. Fail closed.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.
