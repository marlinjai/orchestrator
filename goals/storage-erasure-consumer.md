---
task: storage-erasure-consumer
verify: pnpm run build && pnpm run typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Slice S4 of `docs/plans/2026-07-27-company-isolation.md`: storage-brain consumes auth-brain's signed GDPR erasure webhooks. Reference implementations: lumitra-studio `src/app/api/internal/erasure/` + `src/lib/erasure/` and analytics-platform's consumer; mirror their signature/idempotency/ack contract exactly (HMAC-SHA256 over raw body, same header convention, idempotent by event_id, 2xx only after ALL work, 5xx for retry; payload schemas from `@marlinjai/auth-brain-shared@^1.4.0`, `tenant.erased` carries `workspace_ids`).

## Definition of done

1. **`POST /api/v1/internal/erasure`** on the API app: signature env `STORAGE_ERASURE_WEBHOOK_SECRET` (fail-closed 401/500), bypasses the Bearer middleware but never the signature; idempotency ledger table in BOTH schema sources (numbered D1 migration + Postgres 001).
2. **`tenant.erased`**: resolve SB tenants where `auth_tenant_id` = payload tenant_id OR `auth_workspace_id` IN payload workspace_ids; for each: delete all files (DB rows AND the stored OBJECTS via the storage adapter, batch, tolerate already-deleted), workspaces, upload sessions, then the SB tenant row; ack only when done. Unmatched tenant -> record + ack (nothing to do is success). Cross-tenant isolation asserted in tests.
3. **`user.erased`**: schema audit; SB keys data to tenants not users, so expected verified-no-op with the comment pattern; if any user-keyed artifact exists, handle it.
4. Tests: signature paths, replay no-op, cascade fixture with object-deletion calls asserted (adapter mocked), partial failure retries, both-schema migration covered by the d1 spec pattern.
5. `pnpm run build && pnpm run typecheck && pnpm lint && pnpm test` green. Single conventional commit; lockfile committed if deps change.

## Constraints

- Stay in this worktree. Do not push/publish. Do NOT add the auth-brain registry erasure entry (the operator ships that separately at deploy time). Do not touch S1 auth or S3 items.
- Never log webhook bodies/secrets. No em-dashes or en-dashes. Final message when complete.
