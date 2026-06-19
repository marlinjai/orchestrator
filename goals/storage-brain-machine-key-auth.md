---
task: storage-brain-machine-key-auth
spec: docs/plans/2026-06-17-storage-brain-machine-key-auth.md
verify: pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal

Implement the leaf spec at `docs/plans/2026-06-17-storage-brain-machine-key-auth.md`: the Storage
Brain Worker API authenticates machine callers via auth-brain-issued service-account keys
(`verifyApiKey` -> `can`), alongside the existing legacy `api_key_hash` tenant path as fallback.
First cut supports WORKSPACE-scoped keys only (1:1 to an SB tenant via `auth_workspace_id`);
broader scopes are explicitly rejected. Additive and fail-closed.

## Read first

- The spec in full (scope decision, compound auth flow, files, degradation, tests).
- Existing auth to extend, not break:
  - `packages/api/src/middleware/auth.ts` (`createAuthMiddleware` + `lookupTenant`)
  - `packages/api/src/adapters/database/d1.ts` (`getTenantByApiKey`, and `getTenantByAuthWorkspaceId`
    added in slice 2A)
  - `packages/api/src/env.ts`, `packages/api/wrangler.toml`
- The slice-2A dashboard auth-brain client (`packages/dashboard/src/lib/auth-brain.ts`) and
  analytics-platform's client as the singleton pattern to mirror for the Worker.
- auth-brain SDK contract (published `@marlinjai/auth-brain-sdk@^1.1.0`):
  - `client.verifyApiKey(apiKey) -> ApiKeyVerifyResponse | null` (principal.type/id/scope/role)
  - `client.can(subjectId, "scope.role", resource, { subjectType: 'service_account' }) -> boolean`

## Definition of done

- Everything in the spec body. `pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test`
  all green (the new CI verify.yml enforces the same; keep lint green, src stays strict).
- Compound middleware: legacy key first (local), auth-brain `verifyApiKey` fallback (network).
- Workspace-scoped key + `can(...,'workspace.member',...)=true` -> resolves the bound SB tenant and
  authenticates; `can=false` -> 403; non-workspace scope -> 403 deferred-scope; unknown/expired ->
  fall through to legacy then 401; auth-brain error/timeout -> fail-closed (never allow).
- Degradation: worker boots and legacy auth works with `AUTH_BRAIN_URL` unset (auth-brain branch
  skipped).
- Tests cover every branch above (mock `verifyApiKey` + `can`).
- Spec frontmatter `status: draft` -> `status: done`. Single commit, conventional message with WHY.

## Constraints

- Stay in this worktree. Do not push. Additive/non-breaking: legacy `getTenantByApiKey` path and
  all existing tenant routes must work unchanged; existing auth tests must still pass.
- Do NOT support tenant/tenant_group-scoped keys on this path (reject with a clear 403). Do NOT
  add per-tenant dashboard filtering or remove the legacy path.
- Add `@marlinjai/auth-brain-sdk@^1.1.0` (published) to the api package deps. It is fetch-based and
  Workers-compatible.
- New env vars (`AUTH_BRAIN_URL`, `OPENFGA_API_URL`, `OPENFGA_STORE_ID`) are OPTIONAL: absent ->
  skip the auth-brain branch, never crash.
- No em-dashes or en-dashes in any code/comment/doc.

## Notes

- The API is Hono on Cloudflare Workers; the auth-brain client must be fetch-based (no Node deps).
- File any genuinely out-of-scope discovery as an `open_thread`, not a bare TODO.
