---
task: mt-14
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-03]
verify: 'pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build && ! grep -rnE "requireAdmin|requireAdminAction|verifyAdminCookie|INTERIM_WORKSPACE_ID|STOREFRONT_PRINCIPAL|FRAMER_CLONE_ADMIN_SECRET" src --include="*.ts" --include="*.tsx" | grep -v "/__tests__/"'
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **MT-14** (section "MT-14 - Remove the interim admin secret") — SECURITY-CRITICAL. Delete the parallel single-secret super-admin that currently guards everything except `/api/projects/publish`, and replace it with the real auth-brain path (`getVerifiedSession`/`resolveActiveScope`/`authenticateRequest`, threading the per-request session workspace). In multi-tenant the interim guard is a global super-admin that writes to ONE constant workspace regardless of who is logged in — a hard isolation hole.

The verify gate enforces the core removal: `grep -rE "requireAdmin|requireAdminAction|verifyAdminCookie|INTERIM_WORKSPACE_ID|STOREFRONT_PRINCIPAL|FRAMER_CLONE_ADMIN_SECRET" src` must return ZERO non-test matches.

## Read first

- The MT-14 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md` and the resolved decision D4.
- `src/server/auth/guard.ts` + `src/server/auth/adminAction.ts` — DELETE both. Symbols to eliminate everywhere: `requireAdmin`, `requireAdminAction`, `verifyAdminCookie`, `INTERIM_WORKSPACE_ID`, `STOREFRONT_PRINCIPAL`, `FRAMER_CLONE_ADMIN_SECRET`.
- The canonical guarded WRITE pattern (Route Handlers with a `Request`): `src/app/api/projects/publish/route.ts` — `getVerifiedSession(req)` → `resolveActiveScope(session)` → `authenticateRequest(req, scope.workspaceId, 'editSite')` → repo call passing `scope`/`scope.workspaceId`. Mirror it.
- The next/headers session-read pattern for SERVER ACTIONS / server components (no `Request`): `src/app/projects/loader.ts` (landed by MT-09) reads `lumitra_session` via `next/headers` `cookies()` then `authBrainClient.verifySession` then `resolveActiveScope`. `src/lib/auth-check.ts` `checkWorkspaceAccess(userId, workspaceId, action)` does the permission check.
- The worklist (recon-confirmed line refs):
  - `src/app/api/cms/collections/route.ts` (POST `requireAdmin` ~:36), `[id]/route.ts` (PATCH ~:53, DELETE ~:85) — Route Handlers, use the publish-route pattern.
  - `src/server/cms/actions.ts` — **29** `requireAdminAction()` call sites (lines incl. 47,56,61,72,85,90,95,102,114,119,124,131,144,149,154,159,164,169,174,181,190,207,212,225,232,245,250,255,279). Server actions: use the next/headers session helper.
  - `src/app/api/ai/cms-agent/route.ts` (~:138) + `undo/route.ts` (~:49) — `verifyAdminCookie(request)`; Route Handlers with `request`, use the publish-route pattern.
  - `src/app/api/commerce/orders/route.ts` — `STOREFRONT_PRINCIPAL` + `INTERIM_WORKSPACE_ID` + `can(...)` (~:64-73, :155). See D4 below.
  - `src/server/commerce/inventory/reserve.ts` — `DEFAULT_WORKSPACE_ID='default'` (:48, :296); reconcile (remove if vestigial under schema-isolation, or thread the resolved value).
- `getCmsWriteRepository(workspaceId)` / `getCmsRepository(workspaceId)` (parameterized by MT-03) — thread the real `scope.workspaceId`.

## Definition of done

1. **Delete** `src/server/auth/guard.ts` and `src/server/auth/adminAction.ts`.

2. **Shared next/headers auth helper** — create `src/server/auth/requireWorkspaceScope.ts` exporting `requireWorkspaceScope(action: FramerAction): Promise<TenantScope>`: read `lumitra_session` via `next/headers` `cookies()` → `authBrainClient.verifySession` → `resolveActiveScope` → permission check (`checkWorkspaceAccess(userId, scope.workspaceId, action)` / `can`). On no session / no workspace / not permitted, THROW a typed error (e.g. reuse/define an `AuthError` carrying a 401/403 status) — fail-closed, never fall back to a constant workspace. The 29 server actions use this.

3. **CMS write ROUTES** (`collections/route.ts` POST, `[id]/route.ts` PATCH+DELETE): replace `requireAdmin(req)` with the publish-route flow (`getVerifiedSession` → `resolveActiveScope` → `authenticateRequest(req, scope.workspaceId, 'editSite')`), and thread `scope.workspaceId` into `getCmsWriteRepository(scope.workspaceId)`. Track-0 envelope (401/403/400/404/500).

4. **CMS server ACTIONS** (`src/server/cms/actions.ts`, all 29 sites): replace `await requireAdminAction()` with `const scope = await requireWorkspaceScope('editSite')` and use `getCmsWriteRepository(scope.workspaceId)` / `getCmsRepository(scope.workspaceId)` (resolve scope ONCE per action). The actions now operate on the session's active workspace, not the `CMS_WORKSPACE_ID` constant.

5. **AI cms-agent routes** (`cms-agent/route.ts`, `undo/route.ts`): replace `verifyAdminCookie(request)` with `getVerifiedSession(request)` → `resolveActiveScope` → `authenticateRequest(request, scope.workspaceId, 'editSite')`, and pass `scope.workspaceId` into the CMS repo/agent. Keep the streaming-boundary auth at the SYNC point (before the detached SSE loop), as today.

6. **Commerce orders route** (`commerce/orders/route.ts`) — per D4 (anonymous storefront orders): REMOVE `STOREFRONT_PRINCIPAL`, `INTERIM_WORKSPACE_ID`, and the `can()` super-principal check. Replace with HOST-derived tenant resolution: resolve the request host via `resolvePublishedSite(host)` (from `@/server/sites/publicResolver`); if it does NOT resolve to a published site → 403/404 (not a valid storefront), else proceed to create the order (the existing `createOrder` + `withTenant('commerce', ...)` flow is unchanged — commerce stays single-schema until MT-18). Do NOT leave any constant-workspace super-principal. NOTE/DEFER explicitly (this is a documented, justified deferral, not silent tech debt): the full D4 guest-customer DB model + per-tenant commerce schema is MT-18 (it needs prisma schema changes). MT-14's job is ONLY to remove the super-principal and gate on a valid host.

7. **Reconcile constants**: `INTERIM_WORKSPACE_ID` is gone (deleted with guard.ts). `DEFAULT_WORKSPACE_ID` in `reserve.ts`: remove if it is vestigial under schema-isolation, else thread the real value. `CMS_WORKSPACE_ID` STAYS as the dev/seed default (do not remove it; MT-03 owns it).

Tests: a CMS write with a workspace-A session cannot mutate workspace-B collections; an unauthenticated CMS write returns 401. Update the existing `write-routes.test.ts` (it mocks the OLD `requireAdmin`) and `actions.test.ts` (mocks `requireAdminAction`) to the new session-based auth (mock `@/lib/auth-brain` + `next/headers`, like MT-09's loader test). Delete the now-orphaned `guard.test.ts` / `adminAction.test.ts`.

Plus the always-on + security gate: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass AND the grep gate (zero non-test matches of the 6 symbols). Single conventional commit e.g. `refactor(auth): remove interim admin secret, switch all writes to real auth-brain scope (MT-14)`.

## Constraints

- Stay in this worktree. Do NOT touch the render-path tenancy (MT-13) or `(site)/layout.tsx` (MT-15). Do NOT add the per-tenant commerce schema or a guest-customer table (MT-18).
- `CMS_WORKSPACE_ID` must remain (as a default). The grep gate does NOT ban it — only the 6 interim-secret symbols.
- Do not push to any remote. Output a final completion message.

## Notes

- The big mechanical chunk is the 29 server-action sites. Resolve scope once per action via `requireWorkspaceScope('editSite')`; keep it DRY.
- Data-visibility nuance (expected, correct): CMS writes now land in the session's ACTIVE workspace, not `'framer-clone'`. That is the multi-tenant end state; do not try to migrate seeded demo content here.
- The client `CmsGrid`/`CmsWorkspaceOverlay` pass `workspaceId={CMS_WORKSPACE_ID}` — leave them (MT-03 decision); they are the editor's client prop, not the server auth path.
