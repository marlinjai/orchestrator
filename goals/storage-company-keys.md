---
task: storage-company-keys
verify: pnpm run build && pnpm run typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Slice S1 of `docs/plans/2026-07-27-company-isolation.md` (in this repo; READ IT FIRST, its findings table and target model are binding): storage-brain accepts COMPANY-scoped auth-brain keys, requires the `storage` app grant, and closes the auth gaps the recon found. Existing legacy tenant keys and workspace-scoped keys keep working during the migration (S2 retires them; not this slice).

## Read first

- `docs/plans/2026-07-27-company-isolation.md` (binding) and `docs/plans/2026-06-17-storage-brain-machine-key-auth.md` (the prior slice this extends)
- `packages/api/src/middleware/auth.ts` (the two-stage auth), `packages/api/src/lib/auth-brain.ts` (hand-rolled verify fetch to REPLACE with SDK `verifyApiKey`; `@marlinjai/auth-brain-sdk` >= 1.3.0 exposes it and the scope carries `app_grants`)
- `packages/api/src/routes/public-download.ts` (Bearer branch bypasses auth-brain keys: fix), `packages/api/src/migrations/001_init.sql` AND `packages/api/migrations/*.sql` (BOTH schema sources must change in sync; d1.spec.ts covers only the numbered dir)
- `packages/shared/src/database-adapter.ts`, `packages/api/src/adapters/database/{postgres,d1}.ts`
- CI order: `.github/workflows/verify.yml` runs build -> typecheck -> lint -> test (build first so shared/sdk emit types); the verify gate above mirrors it.

## Definition of done

1. **Schema (both sources + adapters)**: `tenants.auth_tenant_id` (nullable, indexed, unique among live rows) mapping a storage tenant to an auth-brain COMPANY; `upload_sessions.tenant_id` (nullable, backfillable) with the token-only upload route stamping it. Adapter methods `getTenantByAuthTenantId` etc. for both Postgres and D1.
2. **Auth middleware**: bump `@marlinjai/auth-brain-sdk` to `^1.4.0` (lockfile committed); replace the hand-rolled verify fetch with SDK `verifyApiKey`. Accept THREE credential classes, tried in order: legacy tenant key (unchanged), auth-brain `workspace`-scoped key (unchanged mapping via `auth_workspace_id`), NEW `tenant`-scoped key resolving via `auth_tenant_id`. For BOTH auth-brain classes, require `'storage'` in the scope's `app_grants` (fail closed 403 with a distinct log line; missing field entirely = version-skew log pattern). `tenant_group`-scoped keys stay rejected.
3. **Public download fix**: the Bearer branch on `GET /files/:fileId/download` goes through the SAME compound auth as the middleware (legacy + both auth-brain classes + grant check), not the legacy-only lookup.
4. **Repoint tooling for S2**: `scripts/repoint-tenant.ts` taking `--map oldTenantId=newTenantId` pairs: transactional per pair across `files`, `workspaces`, `upload_sessions`; idempotent; prints per-table counts AND the list of file ids whose permanent URLs break (tokens sign `tenantId:fileId`), per the plan's caveat. No hardcoded ids.
5. **Tests** (bare vitest, existing mock style, extend `auth.spec.ts`): tenant-scope key resolves and is scoped to its mapped tenant; ungranted company 403 + log; skew case; workspace-scope path unchanged; legacy path unchanged; download accepts an auth-brain key now; cross-tenant isolation assertions (key for tenant A cannot read B's file via files routes AND the download route); upload_sessions stamping; repoint script mapping logic.
6. `pnpm run build && pnpm run typecheck && pnpm lint && pnpm test` green at root. Single conventional commit explaining the WHY. If the SDK bump changes lockfile, commit it.

## Constraints

- Stay in this worktree. Do not push or publish.
- Do NOT retire legacy keys, split tenants, touch the webhook, URL secrets, or CORS (slices S2/S3), or build the erasure consumer (S4).
- Never log keys, tokens, or signatures. Fail closed.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.
