---
task: studio-tenant-scoped-keys
verify: pnpm db:generate && pnpm test && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Replace Studio's global machine credential with tenant-scoped auth-brain API keys, so a machine caller's company comes from its VERIFIED credential, never from a self-asserted header. Today (post tenant-isolation slice) a machine caller presents the global `SERVICE_TOKEN` and names any enabled company via `x-studio-tenant-id`; any token holder can act on ANY company. That does not hold up for true multi-tenancy and nothing is deployed yet, so it is removed outright, not deprecated. This is Slice 3b of the Studio company isolation plan; it does NOT depend on the parallel auth-brain slice (the verification endpoint and SDK method already exist on main).

## Read first

- `src/lib/auth/verifyRequest.ts` (current bearer branch: SERVICE_TOKEN/SERVICE_TOKEN_NEXT dual-accept + `x-studio-tenant-id`; this whole mechanism is what you remove)
- `src/lib/auth/can.ts` / `guardMutation` and every service-caller call site (the `kind: 'service'` handling)
- `src/lib/auth/auth-brain.ts` (SDK client; `verifyApiKey(apiKey)` resolves a key to `{ principal, scope }` or null/throws; fail closed)
- `src/lib/tenant/access.ts` (`isTenantEnabled`)
- `src/app/api/admin/tenants/route.ts` (ADMIN_API_KEY surface; UNCHANGED, it is a distinct operator credential)
- `src/lib/tenant/isolation.spec.ts`, `src/lib/auth/__tests__/*.spec.ts`, `src/middleware.spec.ts` (suites you extend/rewrite)
- `docs/internal/service-token-rotation.md` (obsolete after this; see DoD)

## Definition of done

1. **Bearer branch rewrite** in `verifyRequest`: a presented `Authorization: Bearer <token>` (on non-admin routes) is resolved via the auth-brain SDK `verifyApiKey`:
   - key resolves AND `scope.type === 'tenant'` AND that tenant is enabled (`isTenantEnabled`) -> `{ kind: 'service', tenantId }` (the AuthResult service variant now CARRIES its tenant)
   - key resolves but scope is `workspace`/`tenant_group` -> reject 401 (Studio accepts company-scoped keys only; do not silently widen or narrow scope)
   - key resolves but tenant not enabled -> `{ kind: 'none', reason: 'no-tenant-access' }` (403 at the boundary)
   - unknown/revoked key, auth-brain unreachable, or any thrown error -> `{ kind: 'none', reason: 'bad-bearer' }` (fail closed, never log the key)
2. **Removal, complete**: `SERVICE_TOKEN` / `SERVICE_TOKEN_NEXT` env handling, the constant-time compare machinery for them, `x-studio-tenant-id` parsing, and every reference (code, tests, env examples, docs). `docs/internal/service-token-rotation.md` is deleted or rewritten to describe key revocation via auth-brain (keys are revoked + reminted there; Studio holds no machine secret of its own anymore). No parked "legacy" code path.
3. **Scoped service semantics**: everywhere the previous slice used the header-derived tenant for service callers (stamping creates, read filters, guardMutation) now uses `auth.tenantId` from the verified key. A service caller is scoped to exactly its one company; reads outside it are absent (404), writes denied. Admin routes (`/api/admin/tenants`) still require `ADMIN_API_KEY` and reject ordinary api-keys.
4. **Tests**:
   - a tenant-scoped key acts only on its company: extend `isolation.spec.ts` so key-A cannot list/get/mutate company B data (absent, no existence leak)
   - workspace-scoped and tenant_group-scoped keys are rejected; disabled-tenant key gets 403; revoked/unknown key or auth-brain failure gets 401 (fail-closed, SDK mocked to throw)
   - creates via a service key stamp the key's tenant; the removed header is now ignored everywhere (a request carrying `x-studio-tenant-id` for a DIFFERENT tenant than its key still acts on the key's tenant)
   - admin surface: ordinary api-key rejected, ADMIN_API_KEY still works
   - middleware suite updated; all existing suites green
5. `pnpm db:generate && pnpm test && pnpm lint` green.
6. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push.
- Do not touch the ADMIN_API_KEY surface's semantics, the browser-session path, the StudioTenant model, or the data-scoping filters beyond swapping the service caller's tenant source.
- Do not add caching of key verifications in this slice (the session path already round-trips auth-brain per request; keep symmetry and simplicity).
- Never log bearer values, keys, or auth-brain responses on any path.
- No em-dashes or en-dashes anywhere.
- When done, output a final message that the task is complete.

## Notes

- Ops (PR description, not code): after deploy, machine consumers (the lumitra-studio-batch skill, lola-stories client) must switch from SERVICE_TOKEN to a tenant-scoped key minted for Marlin's company; their Infisical secrets get replaced by the operator. Note this explicitly.
- If `AUTH_BRAIN_URL` is unset in tests, mock the SDK client seam (`getAuthBrainClient`) as the existing auth specs do.
