---
task: studio-tenant-isolation
verify: pnpm db:generate && pnpm test && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Make auth-brain companies (tenants) the isolation boundary in Lumitra Studio. Today Studio gates entry on membership of ONE hardcoded workspace slug (`lumitra-studio`) and keeps ALL brands/projects in a single unscoped pool: every member sees and can edit everything. After this slice: any auth-brain user whose company has been explicitly ENABLED for Studio can log in, and every brand/project/run is stamped with and filtered by the company (tenant) it belongs to. Two users in different companies are fully invisible to each other. This is Slice 2 of the "Studio company isolation" plan; it does NOT depend on the auth-brain slice (the session payload already carries `tenants[]`).

## Read first

- `src/lib/auth/verifyRequest.ts`, `src/lib/auth/workspace.ts`, `src/lib/auth/can.ts`, `src/middleware.ts` (the current two-layer auth: outer slug gate, inner OpenFGA workspace check)
- `src/lib/auth/auth-brain.ts` (SDK client; `verifySession` returns `{ user, tenants[], workspaces[], active_tenant, active_workspace }` where tenants carry `{ id, ..., role }`)
- `prisma/schema.prisma` (`Brand`, `Project`, `WorkflowRun`; CRITICAL: `Project.workspaceId` is a STORAGE BRAIN bucket ref, not an auth-brain workspace; leave it alone and do not confuse the two)
- `src/lib/brand/repository.ts` (`listBrands` is an unfiltered findMany), `src/app/api/brands/route.ts`, and every other read path for brands/projects/sessions/runs/assets
- `vitest.middleware.config.ts` + existing middleware tests
- Repo CLAUDE.md

## Definition of done

### 1. Access model

- New Prisma model `StudioTenant`: `tenantId String @id`, `enabledAt DateTime @default(now())`, `enabledBy String`. A company may use Studio iff a row exists. This is the cost gate: open auth-brain signup must NOT grant Studio compute by itself.
- Admin machine surface (agent-first rule): `GET/POST/DELETE /api/admin/tenants` gated by `Authorization: Bearer ${ADMIN_API_KEY}` (new env var; constant-time compare, minimum length 32, same discipline as the SERVICE_TOKEN compare in `verifyRequest.ts`). POST body `{ tenantId }` enables, DELETE disables, GET lists. These routes are exempt from the browser session gate but NOT reachable with the ordinary SERVICE_TOKEN.
- `verifyRequest` user branch: valid session -> intersect `session.tenants[]` with enabled StudioTenant rows -> `AuthResult` user variant becomes `{ kind: 'user', email, userId, tenantIds: string[], activeTenantId: string | null }` where `tenantIds` are the ENABLED tenants the user belongs to and `activeTenantId` is `session.active_tenant.id` when that tenant is in `tenantIds`, else the first enabled tenant, else null. Zero enabled tenants -> `{ kind: 'none', reason: 'no-tenant-access' }`.
- Delete the workspace-slug gate (`findStudioWorkspace`, `STUDIO_WORKSPACE_SLUG`, `DEFAULT_STUDIO_WORKSPACE_SLUG`) and the `no-workspace-access` reason; middleware routes `no-tenant-access` to a "request access" page (replace/extend the existing `no-access` page) that tells the user their account exists but no company is enabled for Studio yet, and who to contact. No dead ends.
- Keep the dev bypass (`AUTH_DEV_USER_EMAIL`, development only) working: it yields `tenantIds: []`, `activeTenantId: null`, and read/write paths must treat the dev bypass as unscoped in development exactly as broadly as today (do not break local dev).
- Replace the OpenFGA workspace `can()` check in `can.ts`: for user callers, authorization is now session-derived tenant membership (the target resource's `tenantId` must be in `auth.tenantIds`). Keep the fail-closed shape and the `guardMutation` single-line route ergonomics. The `STUDIO_PERMISSIONS` action vocabulary stays, but `requires` maps to tenant membership. (All tenant roles owner/admin/billing_admin/member may write; there is no viewer at tenant level.)
- Service callers (`SERVICE_TOKEN` bearer): every service request that reads or writes tenant-scoped data MUST name its tenant via an `x-studio-tenant-id` header (or body field where a header is impossible); the value must be an ENABLED tenant or the request fails 400 (unknown/missing) / 403 (not enabled). No implicit all-tenant access on the normal service surface.

### 2. Data scoping

- Prisma: add nullable `tenantId String?` (+ `@@index([tenantId])`) to `Brand`, `Project`, and `WorkflowRun` (WorkflowRun keeps its existing `workspaceId` provenance field untouched). Nullable is deliberate: NULL means "legacy, not yet backfilled" and is INVISIBLE to every tenant-scoped query. Migration file included (`prisma/migrations/`).
- Backfill script `scripts/backfill-tenant.ts` (runnable via `infisical run`-wrapped package script like the existing backfills): takes `--tenant-id <uuid>`, stamps every NULL `tenantId` row across the three tables, prints counts, idempotent. Do NOT hardcode any real tenant UUID anywhere.
- Every read path filters by the caller's tenants: `listBrands`/get-brand, project reads, generation/chat session reads, run reads, asset listing reads that are brand/project-derived. A cross-tenant or unknown id returns 404 (no existence leak), never 403.
- Every create stamps `tenantId` from `activeTenantId` (user) or the validated `x-studio-tenant-id` (service). A user create with `activeTenantId: null` outside dev bypass is a 400 with a clear error.
- Listing semantics: a user sees the union of all their enabled companies' data (no active-only filtering on reads this slice).

### 3. Tests

- Isolation: user A (tenant TA) cannot list, get, mutate, or infer existence (404 not 403) of user B's (tenant TB) brands/projects/runs; covered for both browser-session and service-token paths.
- Gate: session with no enabled tenant -> no-tenant-access; enabling via the admin API flips access; disabling revokes on next request. ADMIN_API_KEY: wrong/short/missing key rejected; ordinary SERVICE_TOKEN rejected on admin routes.
- Legacy rows: NULL `tenantId` rows are invisible to scoped reads; backfill stamps them and they appear.
- Stamping: user create stamps activeTenantId; service create without the header 400s; with a disabled tenant 403s.
- Middleware suite (`vitest.middleware.config.ts`) updated for the new gate and the request-access page redirect.
- Existing suites stay green.

### 4. Ops notes (in the PR description, not code)

- Deploy order: migrate -> deploy -> enable Marlin's tenant via POST /api/admin/tenants -> run backfill with Marlin's tenant id -> verify. Until backfill runs, scoped reads return empty (by design, no crash).
- New env var: `ADMIN_API_KEY` (placeholder to be scaffolded in Infisical by the operator, never a real value in code).

### 5. Gates

- `pnpm db:generate && pnpm test && pnpm lint` green.
- Single conventional commit on this branch explaining the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it. Do not push.
- Do not rename or repurpose `Project.workspaceId` (Storage Brain bucket ref). Do not remove `WorkflowRun.workspaceId`.
- Do not touch the generation engine, providers, or rendering code beyond threading tenant scope through reads/writes.
- Do not weaken the service-token or session verification discipline (constant-time compares, fail-closed, never log credentials).
- No em-dashes or en-dashes anywhere in code, comments, or the commit message.
- When done, output a final message that the task is complete.

## Notes

- The auth-brain SDK needs NO changes: `verifySession` already returns `tenants[]` with roles and `active_tenant`.
- If a read path turns out to be genuinely tenant-agnostic (e.g. static config, health), leave it; the boundary is user data: brands, projects, sessions, runs, assets.
- If the OpenFGA client import becomes unused after the `can.ts` rewrite, remove the dead wiring in the same commit (no parked code).
