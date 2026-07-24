---
task: authbrain-company-api-keys
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1500
---

# Goal

Let a company owner/admin mint and revoke API keys for THEIR company (tenant) in auth-brain, self-serve. Today service accounts + API keys exist but are only creatable via the ADMIN_API_KEY machine API; a company owner has no way to get a machine credential for their own company. This is Slice 3a of the Studio company isolation plan: these tenant-scoped keys become the ONLY machine credential Studio accepts (Slice 3b, in lumitra-studio, runs in parallel and needs no code from this slice).

## Read first

- `packages/app/src/lib/flows/api-keys.ts` (`issueApiKey`, `revokeApiKeyForServiceAccount` and their invariants; reuse, do not fork)
- The service-account creation flow used by `packages/app/src/app/api/admin/machine/service-accounts/route.ts` (reuse the same flow functions)
- `packages/app/src/app/api/verify/api-key/route.ts` (how a key resolves to principal + scope; nothing here changes, read for the contract)
- `packages/app/src/app/api/orgs/route.ts` + `src/lib/flows/companies.ts` (the just-merged user-facing company surface whose auth + CSRF pattern you mirror exactly)
- `packages/app/src/app/settings/companies/` (the page you extend)
- Migrations `004`+ for service_accounts / api_keys table shapes

## Definition of done

1. **Routes** (session cookie + CSRF, mirroring `api/orgs`; authorization = caller holds an OWNER or ADMIN `tenant_membership` on the target tenant, checked in-transaction; anything else is 404 for unknown/foreign tenant, 403 for insufficient role):
   - `POST /api/orgs/[tenantId]/api-keys` body `{ name }`: creates a tenant-scoped service account (scope_type `tenant`, scope_id = the tenant) named after the key, issues one API key via the existing flow, returns `201` with the PLAINTEXT key exactly once plus its metadata (id, prefix, created_at). The plaintext is never logged and never retrievable again.
   - `GET /api/orgs/[tenantId]/api-keys`: lists the tenant's keys (id, name, prefix, created_at, revoked_at), never plaintext or hashes.
   - `DELETE /api/orgs/[tenantId]/api-keys/[keyId]`: revokes via the existing flow; missing/foreign/already-revoked is 404.
   - Audit events + outbox events consistent with what the admin machine path emits.
2. **UI**: the `settings/companies` page gains an API-keys section per company (visible only when the caller's role on that company is owner/admin): list, create (name field, plaintext shown once with a copy control and a "you will not see this again" note), revoke with confirm. Errors surfaced; no dead ends.
3. **Tests** (vitest, existing patterns; Docker-free unit coverage plus integration where the harness supports it):
   - owner and admin can mint; member cannot (403); non-member and unknown tenant read as 404 (no existence leak); unauthenticated 401; CSRF failure rejected
   - minted key verifies through the existing `verifyApiKey` flow and carries scope_type `tenant` + the right scope_id
   - revoked key stops verifying; revoke of foreign/unknown key is 404
   - listing never returns plaintext or hash material
4. `pnpm test && pnpm typecheck && pnpm lint` green at repo root.
5. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push.
- Reuse the existing flows for service-account creation, key issuance, and revocation; if a flow needs a small extension (e.g. a caller-supplied name), extend it in place rather than duplicating.
- Do not change the `api/verify/api-key` contract, the admin machine API, or the SDK/shared published surface.
- Never log or persist plaintext keys beyond the single creation response. Fail closed on every path.
- No em-dashes or en-dashes anywhere.
- When done, output a final message that the task is complete.

## Notes

- One service account per key (named after the key) keeps revocation trivially per-key and matches the existing scope model; do not build key-rotation-within-account machinery.
- The integration spec Docker probe pattern from `src/lib/flows/companies.spec.ts` (ping-based `dockerReachable`) is the template for any new DB-backed spec.
