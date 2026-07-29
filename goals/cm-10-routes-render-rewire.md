---
task: cm-10
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
depends_on: [cm-06, cm-07, cm-08, cm-09, cm-12]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **CM-10** (section "### CM-10 — API routes rewired (render + D4 orders + read routes)" of `docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md`, plus §3.4 + §3.5), as the **MIGRATE / FLIP step of the EXPAND-CONTRACT strategy Marlin decided 2026-06-27**. This is the cutover commit: the 4 commerce API routes and the SSR render path stop calling the OLD Prisma path and start calling the NEW Kysely funcs (added by CM-06..CM-09) with a scoped handle resolved from the request host.

**Read this framing first, it changes the whole shape of the spec:** CM-06..CM-09 ran EXPAND: they ADDED new Kysely funcs ALONGSIDE the untouched old Prisma ones (suggested temp suffixes `*Kysely` / `getCommerceServerRepositoryDb` / `createOrderKysely`). This spec is where the CALLERS flip. You rewire the routes + `page.tsx` to call those new funcs through `commerceTenantDb(resolveTenantGroupForSite(site))`. You do NOT delete the old path here: `withTenant.ts`, the old `commerce` schema, the old Prisma repo funcs, the old `getCommerceServerRepository(prisma, schema)`, and `resolveCommerceSchemaForSite` all STAY intact so a single-commit revert re-points to the old path (the §9 reversible cutover). The CONTRACT step (CM-13) deletes the old path and renames the temp-suffixed new funcs to canonical AFTER the demo is verified green on `tg_<demo>` (CM-12). Deleting `withTenant.ts` here would break the seed (it still imports `withTenant` until CM-12 flips it), so the delete is deliberately deferred to CM-13.

## Read first (the seams being flipped)

- The plan's CM-10 section + §3.4 ("Rewiring the render path", the `getCommerceServerRepositoryDb(commerceTenantDb(resolveTenantGroupForSite(site)))` shape) + §3.5 ("The D4 orders route resolves tenant-group from the host") + §9 (reversible cutover: old `commerce` schema retained until CM-13).
- The render seam: `src/server/commerce/tenant.ts` (today `resolveCommerceSchemaForSite(site)` returns the constant `COMMERCE_SCHEMA`; you ADD `resolveTenantGroupForSite(site): TenantGroupId` = `assertTenantGroupId(site.tenantGroupId)` ALONGSIDE it, keeping the old function). `src/app/(site)/[...slug]/page.tsx` lines ~44-45 + ~137-140 (the `getCommerceServerRepository(undefined, resolveCommerceSchemaForSite(site))` call -> `getCommerceServerRepositoryDb(commerceTenantDb(resolveTenantGroupForSite(site)))`).
- The 4 routes:
  - `src/app/api/commerce/orders/route.ts` (the D4 write seam: gates on `resolvePublishedSite(host)` -> 403, `.strict()` zod body, a local `resolveLines(tx, lines)` under `withTenant`, `createOrder(prisma, cart)`, and the order readback under `withTenant`).
  - `src/app/api/commerce/products/route.ts` + `src/app/api/commerce/products/[handle]/route.ts` (each `withTenant`-wraps a read repo call + `pricingRepository.resolvePrice(tx, variant.id, { currency })`).
  - `src/app/api/commerce/inventory/route.ts` (a raw `SELECT available_quantity` on `Prisma.raw('"commerce"."inventory_level"')` at ~:43/:61 under `withTenant`).
- The NEW funcs you flip TO: CM-06 `pricingRepositoryKysely` (and `catalogRepositoryKysely` if a route needs it); CM-07 `getCommerceServerRepositoryDb` + `commerceReadRepositoryKysely`; CM-08 the NEW `*Kysely` reserve (consumed inside createOrder, not directly by routes); CM-09 `createOrderKysely(db, cart)`.
- The base + scoping API: CM-02's `src/server/commerce/db.ts` (`getCommerceBase()`, `commerceTenantDb(tg)`, the re-exported `tenantDb`), `node_modules/@marlinjai/tenant-db/dist/*.d.ts` (`assertTenantGroupId`, `tenantSchemaRef`, `TenantGroupId`), CM-05's `CommerceDB`. `src/server/sites/publicResolver.ts` (`PublishedSite` already selects `workspaceId` + `tenantGroupId`).

## Definition of done (MIGRATE: flip callers to the new path, delete nothing)

- `tenant.ts`: ADD `export function resolveTenantGroupForSite(site: Pick<PublishedSite,'workspaceId'|'tenantGroupId'>): TenantGroupId { return assertTenantGroupId(site.tenantGroupId); }`. KEEP the existing `resolveCommerceSchemaForSite` + its `COMMERCE_SCHEMA` import intact (CM-13 deletes them once nothing calls them).
- The SSR render path `src/app/(site)/[...slug]/page.tsx`: import `resolveTenantGroupForSite` + the base helpers + `getCommerceServerRepositoryDb`, and call `getCommerceServerRepositoryDb(commerceTenantDb(resolveTenantGroupForSite(site)))` (the CM-07 new scoped-handle factory). Drop the `resolveCommerceSchemaForSite` + old `getCommerceServerRepository` imports from this file.
- The orders route: derive `const db = commerceTenantDb(resolveTenantGroupForSite(site));` and flip `resolveLines` to the scoped `db` (port its `productVariant.findFirst` + `inventoryItem.findFirst` SKU bridge to structured Kysely selects), call `createOrderKysely(db, cart)`, and turn the order readback into a structured `db.selectFrom('order').select(['total','currency_code']).where('id','=',orderId).executeTakeFirst()` (no `withTenant`). The 403-on-unpublished-host gate and the `.strict()` body (rejecting any price/stock/total key) are UNCHANGED. Drop the route's `withTenant` import.
- The 3 read routes (products, products/[handle], inventory): resolve the tg from the host gate the same way, build `const db = commerceTenantDb(resolveTenantGroupForSite(site));`, and call the NEW Kysely funcs (`getCommerceServerRepositoryDb(db)` / `commerceReadRepositoryKysely` for catalog reads, `pricingRepositoryKysely.resolvePrice(db, variant.id, { currency })` for pricing). The inventory route's raw `SELECT available_quantity` becomes a structured `db.selectFrom('inventory_level').select('available_quantity').where('inventory_item_id','=',...).where('location_id','=',...)` (reading the GENERATED column directly, plan §5.2 site #9), OR a `tenantSchemaRef`-qualified raw if a structured form does not fit; no bare `inventory_level` in `sql\`\``. Drop the `withTenant`/`COMMERCE_SCHEMA`/`Prisma.raw` imports these routes no longer use.
- NOTHING is deleted: `withTenant.ts` STAYS (the seed still imports it until CM-12), the barrel's `export { COMMERCE_SCHEMA, withTenant }` STAYS, the old Prisma repo funcs + old `createOrder` + old `getCommerceServerRepository` STAY, `resolveCommerceSchemaForSite` STAYS, the old `commerce` Postgres schema STAYS. This is the reversible cutover.
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass (the route/render tests are updated to the scoped-handle shape; the orders route still 403s a non-published host and rejects extra body keys). Single conventional commit e.g. `feat(commerce): flip routes + SSR render to scoped tenantDb handle (migrate), old path retained (CM-10)`.

## Constraints

- MIGRATE (flip callers), do NOT delete and do NOT re-port. Files: `src/server/commerce/tenant.ts` (add `resolveTenantGroupForSite`), `src/app/(site)/[...slug]/page.tsx`, the 4 routes under `src/app/api/commerce/`, plus the route/render test updates. Do NOT delete `withTenant.ts` (CM-13), do NOT remove the barrel re-exports (CM-13), do NOT touch the repos themselves (CM-06..CM-09 already added the new funcs), the seed (CM-12), provisioning (CM-11), the migration set (CM-04), or `prisma/schema.prisma` (CM-13).
- The orders route stays the storefront write seam: keep the `resolvePublishedSite(host)` 403 gate and the `.strict()` zod body verbatim. Checkout STILL stops at order-created (no payment). The server stays the sole author of money + stock.
- Preserve the decided naming: the scoped handle comes from `commerceTenantDb(resolveTenantGroupForSite(site))`; the tg id is validated via `assertTenantGroupId`; raw availability reads (if any) use `tenantSchemaRef`. No `SET LOCAL search_path` anywhere on the new path.
- Keep the SKU-bridge semantics in the ported `resolveLines` exact: variant.sku -> inventory_item.sku, both `deleted_at IS NULL`; a variant with no sku or no live inventory item is a loud error, never a silent zero-stock success.
- Until CM-13, the old `commerce` schema is NOT dropped and the Prisma client (`src/server/db.ts`) stays (CMS still uses it). Do NOT drop or alter the old schema here.
- Do not push to any remote. Output a final completion message confirming: each route + `page.tsx` now calls the NEW Kysely funcs through `commerceTenantDb`, NOTHING was deleted (old path intact, single-commit-revertible), and the orders route still 403s + `.strict()`-rejects.

## Notes

- V1 PLAN-GAP RESOLVED: the v1 CM-10 deleted `withTenant.ts` and edited the barrel. Under expand-contract that delete is wrong here: the seed imports `withTenant` until CM-12 flips it, so deleting it now breaks the whole-program typecheck between CM-10 and CM-12. The delete (and the barrel re-export removal) moves to CM-13. This spec therefore does NOT edit the barrel at all (the new funcs are exported by CM-07 / imported directly from their modules).
- The new funcs you call still carry their temporary `*Kysely` / `*Db` suffixes. CM-13 renames them to canonical and updates the caller lines you write here. Do not pre-rename.
- `resolveLines` (orders route) and the inventory raw read are the two spots that still touched Prisma/`withTenant` at the ROUTE layer (not the repo layer), so they are flipped here, ported to the scoped `db`.
- This is the §9 reversible cutover point. CM-11 provisions `tg_<demo>` and CM-12 backfills it; the live demo must render + check out on `tg_<demo>` before the operator trusts the flip in prod and lets CM-13 drop the old schema. In the worktree the verify gate proves it COMPILES + unit-passes.
