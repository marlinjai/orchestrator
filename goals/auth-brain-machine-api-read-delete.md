---
task: auth-brain-machine-api-read-delete
verify: pnpm typecheck && pnpm lint && pnpm test
# Target repo (--project): a worktree of ERP-suite/projects/lumitra-infra/auth-brain (remote github.com/marlinjai/auth-brain)
# Sourced from backlog item: arbosano... no -- `auth-brain-machine-api-read-and-delete-endpoints` (knowledge-base/backlog/backlog.md)
# Revenue/platform: completes the agent-first machine surface (standing rule). Terminal artifact = DRAFT PR (identity infra, you merge).
---

# Goal

Complete the agent-first machine API surface on auth-brain. The `/api/admin/machine/*` routes have
CREATE (`POST`) but several lack read (`GET`/list) and the workspace/tenant/org routes lack `DELETE`.
Add the missing **GET/list** handlers (the read half an agent needs to discover ids without DB access)
and, where a soft-delete mechanism already exists, the **soft-DELETE** handlers. This is the read/delete
gap the analytics cutover hit (had to read workspace ids straight from Postgres; a stray
`lumitra-analytics` workspace needs a soft-delete). Mirror the existing handler patterns exactly; this is
additive and bounded, no redesign.

## Read first

- `packages/app/src/app/api/admin/machine/workspaces/route.ts` (the POST pattern to mirror: `requireAdminApiKey(req)` gate -> `getDb()` -> `machineActorByEmail` -> repository call -> `handleRouteError`; `export const dynamic = 'force-dynamic'`; zod for input).
- `packages/app/src/app/api/admin/machine/workspaces/route.spec.ts` (the test pattern: `vi.mock('@/lib/db/client', ...)`, `vi.mock` the repositories + `@/lib/admin-api-key`; tests run BARE, no real DB). Mirror this for every new handler.
- `packages/app/src/app/api/admin/machine/memberships/route.ts` and `service-accounts/[id]/route.ts` (the EXISTING `DELETE` handlers: copy whatever deletion semantics they use, soft vs hard, do not invent a new one).
- `src/lib/db/repositories/*` (the repository layer the routes call: tenants, workspaces, orgs, etc.). You will likely ADD `list*` (and where applicable `softDelete*`) functions here, mirroring the existing ones.
- `packages/app/src/lib/admin-api-key.ts` (`requireAdminApiKey`, `machineActorByEmail`) and `src/lib/api/responses.ts` (`handleRouteError`).

## Scope

1. **GET/list (the core, do all of these):** add a `GET` handler to each machine COLLECTION route that lacks one: `workspaces`, `tenants`, `orgs`, `invitations`, `service-accounts`. Each: `requireAdminApiKey(req)` (same gate as POST), parse optional query params with zod (pagination + a tenant/org scope filter where the resource is tenant-scoped), call a repository `list*` function (add it if missing, mirroring existing repo functions), return `NextResponse.json({ items, ... })`. Tenant/workspace-scoped resources MUST be filterable/scoped so a machine actor only lists within its allowed scope, consistent with how POST resolves scope.
2. **Soft-DELETE (workspaces, tenants, orgs) -- ONLY if a soft-delete mechanism already exists:** check how `memberships` / `service-accounts/[id]` DELETE work and whether the schema has a soft-delete column (e.g. `deleted_at`/status). If a soft-delete pattern EXISTS, add `DELETE` handlers for workspaces/tenants/orgs mirroring it (admin-gated, soft only). If deletion would require a NEW schema column / migration on the identity DB, do NOT invent it: ship the GET/list part, and file an `open_thread` describing the schema decision needed (soft-delete column on workspaces/tenants/orgs) for the operator. NEVER hard-delete identity rows.
3. **Tests:** add `route.spec.ts` cases for every new handler, mirroring the existing mocked-DB spec style: list happy-path (200 + shape), the admin-key gate rejecting (401, never touches the db), scope filtering, and for any DELETE added: soft-delete 200, 401 on bad key, not-found path. No real DB (mock `@/lib/db/client` + the repositories).

## Definition of done

- Every machine collection route (`workspaces`, `tenants`, `orgs`, `invitations`, `service-accounts`) has an admin-gated `GET`/list; tenant-scoped resources are scope-filterable.
- Soft-DELETE added for workspaces/tenants/orgs IF a soft-delete mechanism exists; otherwise an `open_thread` filed for the schema decision and GET/list still complete.
- New repository `list*` (+ `softDelete*` where applicable) functions added, mirroring existing ones.
- `pnpm typecheck && pnpm lint && pnpm test` all green (new specs included).
- One conventional commit on the worktree branch describing the WHY (complete the agent-first machine read/delete surface).

## Constraints

- Mirror the existing POST/DELETE handler + spec patterns EXACTLY (auth gate, zod, getDb, repositories, handleRouteError, force-dynamic). Additive only; do not refactor existing routes.
- Admin-gated on EVERY new handler (`requireAdminApiKey`), same as the POST handlers. No new auth bypass.
- SOFT delete only on identity rows, and only if the mechanism already exists; never hard-delete; never invent an identity-schema migration autonomously (escalate that via open_thread instead).
- No secret handling, no deploy, no migration-apply. Stay in the worktree; do not push; do not open a PR (the operator opens the draft PR after review).
- No em-dashes / en-dashes. Conventional-commit message.

## Notes

- This is the read/delete half of the agent-first machine surface ([[agent-first-machine-surface]]): CREATE shipped via #29/#30, service-account principals via #35; this completes discovery (list) + lifecycle (soft-delete).
- The verify runs bare because the route specs mock the db/repositories; if `pnpm test` unexpectedly needs a live DB, prefer scoping the new specs to the mocked pattern rather than wiring a test DB.
