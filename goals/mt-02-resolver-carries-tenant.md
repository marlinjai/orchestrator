---
task: mt-02
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-02** (section "MT-02 - Public resolver carries the tenant"): stop dropping `workspaceId`/`tenantGroupId` when resolving a published site, so the render route (MT-13) can thread per-site tenancy. ADDITIVE ONLY — no behavior change to resolution itself.

## Read first

- The MT-02 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/server/sites/publicResolver.ts` — the `PublishedSite` interface (around lines 37-46) and `resolvePublishedSite`'s `prisma.site.findFirst` `select` block (around lines 108-119). The `Site` model has `workspaceId @map("workspace_id")` and `tenantGroupId @map("tenant_group_id")` (Prisma camelCase field names are `workspaceId`/`tenantGroupId`).
- Any existing test for `publicResolver` (search `src/server/sites/__tests__/` and `test/`).

## Definition of done

In `src/server/sites/publicResolver.ts`:
- Add `workspaceId: string` and `tenantGroupId: string` to the `PublishedSite` interface.
- Add `workspaceId: true` and `tenantGroupId: true` to the `findFirst` `select` of the `Site` row, and include them in the returned mapped object.
- EXISTING behavior is unchanged: still resolves by `subdomain` (via `parseSubdomain` + `siteDomain.findUnique`), still filters `status: 'published'` only, still returns `null` for draft/archived/unknown. Do NOT change `parseSubdomain` or the published-only filter.

Test (extend an existing resolver test if present, else add `src/server/sites/__tests__/publicResolver.tenant.test.ts`):
- Assert the resolved `PublishedSite` object carries the seeded demo site's `workspaceId` and `tenantGroupId`. Mirror the existing resolver test's prisma-mock style (mock `prisma.siteDomain.findUnique` to return `{ siteId }` and `prisma.site.findFirst` to return a row that INCLUDES `workspaceId` and `tenantGroupId`), then assert the returned object surfaces both. If the existing resolver test uses an integration/seeded-DB approach, follow that instead and assert against the seeded demo workspace (`'framer-clone'`) / tenant group (`'demo-tenant-group'`).

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(sites): resolvePublishedSite carries workspaceId + tenantGroupId (MT-02)`.

## Constraints

- Stay in this worktree. Touch ONLY `src/server/sites/publicResolver.ts` and its test(s).
- Do NOT change the render route, CMS repo, or commerce — MT-13 consumes this; this spec only makes the data available.
- Do not push to any remote. Output a final completion message.

## Notes

- This is a tiny, surgical change. The risk is forgetting to add the fields to BOTH the `select` AND the returned object literal (the mapping). Verify both.
- `apiKeyRef` in `PublishedSite` is a server-side REF, never the literal key — do not change that.
