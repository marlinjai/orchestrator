---
task: mt-13
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-02, mt-03]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-13** (section "MT-13 - Thread per-site tenancy through the render path") — SECURITY-CRITICAL CORRECTNESS, not optimization. The SSR render must derive BOTH the CMS workspace (column isolation) AND the commerce tenant/schema from the RESOLVED site row, not from module constants. Without this, N published sites on the wildcard all render ONE global tenant's CMS collections + commerce catalog — a hard isolation bug for any second tenant.

## Read first

- The MT-13 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/server/sites/publicResolver.ts` — `PublishedSite` now carries `workspaceId` + `tenantGroupId` (landed by MT-02).
- `src/app/(site)/[...slug]/page.tsx` — the render route. It calls `renderPublishedPage({ ..., cmsRepo: getCmsRepository(), commerceRepo: getCommerceServerRepository() })`. `getCmsRepository()` is now parameterizable (MT-03): `getCmsRepository(workspaceId)`.
- `src/lib/renderer/server/renderPublishedPage.tsx` — repos are INJECTED by the route (not constructed here); it passes them to `hydrateBindings`.
- `src/server/commerce/repository/read.ts` — `getCommerceServerRepository(prisma = getPrismaClient())` pins `COMMERCE_SCHEMA` into `withTenant(prisma, COMMERCE_SCHEMA, ...)` on every method. `src/server/commerce/withTenant.ts` — `COMMERCE_SCHEMA = 'commerce'`; `withTenant(prisma, schema, fn)` already takes an explicit allowlisted schema.

## Definition of done

In `src/app/(site)/[...slug]/page.tsx` (the render route):
- Pass the resolved site's workspace into the CMS read repo: `getCmsRepository(site.workspaceId)`. This is THE correctness fix — CMS reads now isolate by the resolved site's workspace, not the module constant. No module-constant `CMS_WORKSPACE_ID` may reach a render-path query.
- Pass a commerce tenant/schema DERIVED FROM THE SITE into the commerce repo. Introduce a small `resolveCommerceSchemaForSite(site)` (e.g. in `src/server/commerce/tenant.ts` or alongside the resolver) that — UNTIL MT-18 — maps EVERY site to the single shared `COMMERCE_SCHEMA` ('commerce'), with a clear comment documenting the limitation: "multi-tenant commerce is BLOCKED to one tenant until MT-18; CMS-only multi-tenant sites are fully isolated and may ship now." Thread its result into the commerce repo.

In `src/server/commerce/repository/read.ts`:
- Give `getCommerceServerRepository` an explicit schema param: `getCommerceServerRepository(prisma = getPrismaClient(), schema: string = COMMERCE_SCHEMA)` and pass `schema` into each `withTenant(prisma, schema, ...)` call instead of the hard-coded constant. Default = `COMMERCE_SCHEMA` so existing callers are unchanged. This is the SEAM MT-18 fills; do NOT build the per-tenant schema registry here.

Test (integration, `.itest.ts`, CI runs it):
- Seed TWO published sites in TWO different workspaces, each with its OWN CMS collection content. Assert each subdomain renders ONLY its own CMS data (the regression this spec exists to prevent). If a full SSR integration test is too heavy, at minimum assert that `getCmsRepository(site.workspaceId)` is the call the render route makes (the workspace flows from the resolved site, not a constant) AND an integration test that two workspaces' `listCollections` are isolated.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `fix(render): thread per-site workspace into CMS reads + commerce schema seam (MT-13)`.

## Constraints

- Stay in this worktree. Files: `src/app/(site)/[...slug]/page.tsx`, `src/server/commerce/repository/read.ts`, a small new `resolveCommerceSchemaForSite` helper, and tests. You MAY lightly touch `renderPublishedPage.tsx` only if the repo-injection signature needs it (prefer NOT to — repos are injected at the route).
- Do NOT build the per-tenant commerce schema registry/provisioning (that is MT-18). Only create the seam (a schema param + a site→schema resolver that returns the constant for now).
- Do NOT touch the CMS write routes / admin secret (that is MT-14). Do NOT touch `(site)/layout.tsx` (that is MT-15).
- Do not push to any remote. Output a final completion message.

## Notes

- The two engines use DIFFERENT tenancy mechanisms: CMS isolates by a `workspace_id` COLUMN (so pass `workspaceId`), commerce isolates by Postgres SCHEMA via `SET LOCAL search_path` (so pass a schema). BOTH must be carried from the one resolved Site row.
- This is a hard isolation bug for any second tenant. Correctness over cleverness. The integration test proving two sites don't bleed is the heart of the spec.
