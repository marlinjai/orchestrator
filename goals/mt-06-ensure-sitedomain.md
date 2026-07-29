---
task: mt-06
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-01]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-06** (section "MT-06 - ensureSiteDomain + unpublishProject"): DB-enforced subdomain allocation on first publish (idempotent on re-publish) plus an unpublish path, as new methods on `SiteRepository`. Today the ONLY code that writes a `SiteDomain` is the seed; subdomains are never generated.

## Read first

- The MT-06 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/server/sites/subdomain.ts` (landed by MT-01): `generateSubdomain()`, `isReserved`, `RESERVED_SUBDOMAINS`. Use `generateSubdomain()` for allocation.
- `src/server/sites/repository.ts` — the `SiteRepository` class. Every public method takes `scope: TenantScope` first and calls `assertScope(scope)`. MIRROR the cross-workspace guard: `publishProject` uses `updateMany({ where: { id, workspaceId: scope.workspaceId } })` then `if (result.count === 0) throw new SiteNotFoundError(siteId)`. The constructor holds `this.prisma`.
- `src/server/sites/errors.ts` — `SiteNotFoundError(siteId)` (404), `SiteRepositoryError(code, message, status)` base, `InvalidTenantScopeError`. Add a new typed error here ONLY if needed for exhausted-collision (see below).
- `prisma/schema.prisma` `SiteDomain` — `subdomain String? @@unique`, `customHostname String? @@unique` (both partial-unique on nullable cols), `verificationStatus DomainVerificationStatus @default(pending)` (values `pending|active|failed`), `isPrimary Boolean @default(false)`, denormalised `workspaceId`/`tenantGroupId`, `siteId`. NOTE: `isPrimary` has NO DB uniqueness.
- Prisma `P2002` (unique-constraint violation): `import { Prisma } from '@prisma/client'` and catch `err instanceof Prisma.PrismaClientKnownRequestError && err.code === 'P2002'`.
- Existing repo tests: `src/server/sites/__tests__/repository*.test.ts` and any `*.itest.ts` — MIRROR their style (whether they mock prisma or use testcontainers).

## Definition of done

Add to `SiteRepository`:

`async ensureSiteDomain(scope: TenantScope, siteId: string): Promise<{ subdomain: string }>`:
- `assertScope(scope)` first.
- Verify the site is in this workspace (e.g. `findFirst({ where: { id: siteId, workspaceId: scope.workspaceId }, select: { id: true } })`); if absent → `throw new SiteNotFoundError(siteId)` (NEVER allocate across the boundary).
- If a `SiteDomain` row for this `siteId` already has a NON-NULL `subdomain`, return `{ subdomain }` UNCHANGED (re-publish is a no-op; the URL is STABLE).
- Otherwise allocate: generate `generateSubdomain()`, INSERT a `SiteDomain` (`subdomain`, `verificationStatus: 'active'`, `isPrimary: true`, `workspaceId`/`tenantGroupId` from `scope`, `siteId`). The allocator ALWAYS writes a NON-NULL label (NULL subdomains don't collide and would defeat enforcement).
- Collision handling is DB-ENFORCED, NOT check-then-insert: on Prisma `P2002` against the subdomain unique index, regenerate and retry, BOUNDED (>= 5 attempts). On exhaustion, throw a LOUD error (a typed `SiteRepositoryError` that surfaces as 500, e.g. code `subdomain_allocation_failed`) — never a silent success.

`async unpublishProject(scope: TenantScope, siteId: string): Promise<void>`:
- `assertScope(scope)`; flip `Site.status` back to `'draft'` via scoped `updateMany({ where: { id, workspaceId }, data: { status: 'draft' } })`; `if (count === 0) throw new SiteNotFoundError(siteId)`.
- Do NOT delete the `SiteDomain` row (re-publish reuses the slug — decision D3).

Tests (mirror existing repo test style):
- Idempotency: a site with an existing non-null subdomain returns it unchanged on a second `ensureSiteDomain`.
- DB-enforced collision: simulate a colliding label (mock `siteDomain.create` / `siteDomain.upsert` to throw a `P2002` once, then succeed; or seed a clashing row in an integration test) and assert a retry RESOLVES it and returns a label. Assert exhausted retries throw the loud error.
- Scoped: `ensureSiteDomain` for a siteId in ANOTHER workspace throws `SiteNotFoundError`.
- `unpublishProject` flips status to draft and does NOT delete the `SiteDomain` row; zero-rows throws `SiteNotFoundError`.
- The allocated row always has a non-null `subdomain`, `verificationStatus: 'active'`, `isPrimary: true`, stamped workspace/tenant.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(sites): ensureSiteDomain (DB-enforced allocation) + unpublishProject (MT-06)`.

## Constraints

- Stay in this worktree. Touch ONLY `src/server/sites/repository.ts`, optionally `src/server/sites/errors.ts` (new typed error), and tests. Do NOT modify the publish route — wiring is MT-07.
- The `SiteDomain` write must be scoped + always non-null subdomain. Do NOT introduce a check-then-insert race; rely on the unique index + P2002 retry.
- Do not push to any remote. Output a final completion message.

## Notes

- If the existing repo tests use testcontainers (`*.itest.ts`), the real-P2002 collision test is cleanest there (insert a row with the label, then force the allocator to that label once). If they mock prisma, mock `siteDomain.create` to throw a `P2002` on the first call. Either is acceptable; the in-loop verify runs unit only, CI runs integration.
- `ensureSiteDomain` is what MT-07's publish route calls AFTER `publishProject`. Keep the return shape `{ subdomain }` exactly.
