---
task: cm-07
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
depends_on: [cm-05]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **CM-07** (section "### CM-07 — Read repo (`read.ts`) → Kysely, preserve `CommerceServerRepository` contract" of `docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md`, plus §3.4 + the §5.1 `read.*` rows), using the **EXPAND-CONTRACT (parallel-change) strategy Marlin decided 2026-06-27**.

**Read this framing first, it changes the whole shape of the spec:** the framer-clone verify gate is a WHOLE-PROGRAM typecheck (`tsc --noEmit` + `next build`). The old `getCommerceServerRepository(prisma?, schema)` is called by the SSR render path `src/app/(site)/[...slug]/page.tsx:137-140` (a two-arg call). If you RETYPE that factory in place to take a single scoped `db`, you instantly break `page.tsx` (owned by CM-10) and the verify gate fails. So you do NOT replace in place. You ADD a NEW Kysely read path ALONGSIDE the untouched old Prisma read path: new tx-first Kysely read functions and a new `getCommerceServerRepositoryDb(db)` factory, while `commerceReadRepository` and the old `getCommerceServerRepository(prisma, schema)` stay byte-for-byte intact. Because the old factory keeps its signature, `page.tsx` keeps compiling through this spec, CM-08, and CM-09. CM-10 flips `page.tsx` + the routes to `getCommerceServerRepositoryDb`; CM-13 deletes the old path and renames the new one to canonical. This matches plan §10 ("the old Prisma path is kept intact through CM-12"). This spec is the EXPAND step for the read repo.

## Read first (ground in the REAL read repo + its contract)

- The plan's CM-07 section + §3.4 ("Rewiring the render path") + the §5.1 rows for `read.listProducts/getProductByHandle/listVariants/getPrices/getAvailability`.
- The source you ADD TO but do NOT rewrite: `src/server/commerce/repository/read.ts` (the tx-first `commerceReadRepository`, the `PRODUCT_INCLUDE` / `VARIANT_INCLUDE` graph shapes, the row->DTO mappers `mapProduct`/`mapVariant`/`mapPrice`, and the existing `getCommerceServerRepository(prisma?, schema?)` at ~339-365 that wraps each method in `withTenant`). These STAY as-is so `page.tsx` and the publish hydrator keep compiling.
- The CONTRACT to preserve UNCHANGED: `src/lib/renderer/publish/hydrateBindings.ts` lines 113-129 (`interface CommerceServerRepository`: `listProducts(query?)`, `getProductByHandle(handle)`, `listVariants(productId)`, `getPrices(variantId)`, `getAvailability(variantId, locationId?)`). Do NOT edit this interface. The new factory's RETURN must structurally satisfy it (compile + a structural test). The DTOs: `src/lib/commerce/types.ts` (`ProductPage`, `ProductDTO`, `ProductVariantDTO`, `PriceDTO`, `AvailabilityDTO`, `ALL_LOCATIONS`).
- The barrel: `src/server/commerce/index.ts` (re-exports `getCommerceServerRepository`, `commerceReadRepository`, `CommerceReadRepository`, the type-only `CommerceServerRepository`, and `COMMERCE_SCHEMA, withTenant`). This spec ADDS the new exports here and KEEPS the old. Among the W2 expand trio (CM-07/08/09) ONLY CM-07 touches the barrel (CM-08 reserve and CM-09 order/createOrder are not barrel-exported), so no shared_state collision.
- The typed handle + shape: CM-05's `CommerceDB` (re-exported from `src/server/commerce/db.ts`), CM-02's `src/server/commerce/db.ts` (`getCommerceBase`, `commerceTenantDb`, the re-exported `tenantDb`), and `@marlinjai/tenant-db` (`tenantDb`, `tenantSchemaRef`).
- The Kysely json helper to reproduce the Prisma `include` graph: `jsonArrayFrom` (verify the exact import path against the installed kysely version, e.g. `kysely/helpers/postgres`).
- The isolation-test template: `auth-brain/packages/tenant-db/src/tests/isolation.spec.ts`; the container/provision/TRUST-AUTH setup from CM-04/CM-06 isolation specs.

## Definition of done (EXPAND: add new, keep old)

- NEW Kysely read functions added ALONGSIDE the old object. Add a new tx-first object (suggested `commerceReadRepositoryKysely`, methods `(db: Kysely<CommerceDB>, args)`) in `read.ts`:
  - `listProducts` = a filtered count select (ignoring limit) + a paginated select with the options->values + variant graph assembled via `jsonArrayFrom` (or grouped selects) reproducing the `PRODUCT_INCLUDE` shape EXACTLY (same `deleted_at IS NULL` filters on options/values/variants, same case-insensitive filter ops, same order-by, same `take`-floored-at-0 limit).
  - `getProductByHandle` = `selectFrom('product').where('handle','=',h).where('deleted_at','is',null)` returning the FIRST match (handle is partial-unique, findFirst semantics).
  - `listVariants` = structured select + nested `jsonArrayFrom` for options->optionValue + product.tax_class.
  - `getPrices` = the variant tax_class read + `selectFrom('price')` joined on the variant's price_set.
  - `getAvailability` = variant + SKU bridge + `inventory_level` read; read the GENERATED `available_quantity` column DIRECTLY (CM-04/CM-05) instead of recomputing stocked-reserved in JS, aggregating across locations when no `locationId`.
  - The row->DTO mappers reproduce the conditional spreads (optional fields) and the variant taxClass fallback (variant else product) byte-for-byte. Reuse the existing `mapProduct`/`mapVariant`/`mapPrice` shape or co-locate Kysely equivalents; the DTO output must match `InMemoryCommerceDataSource` field-for-field.
  - Type the new object with a NEW interface co-located IN `read.ts` (do NOT edit `repository/types.ts`: that avoids the CM-09 collision on that file).
- NEW `getCommerceServerRepositoryDb(db: Kysely<CommerceDB>): CommerceServerRepository` added ALONGSIDE the old factory. It receives an ALREADY-scoped handle (the caller passes `commerceTenantDb(tg)` / `tenantDb(getCommerceBase(), tg)`) and each returned method delegates to `commerceReadRepositoryKysely` with that `db`. No `withTenant` wrapping (that whole pattern is gone for the new path). The returned object satisfies `CommerceServerRepository` (compile + a structural test).
- The OLD `commerceReadRepository`, the OLD `getCommerceServerRepository(prisma?, schema?)`, and the `CommerceServerRepository` interface are LEFT UNTOUCHED. `page.tsx` is NOT edited. No existing caller changes. (Sanity: after your change, `git diff read.ts` shows the new object + new factory as ADDITIONS, not a rewrite of the existing exports.)
- The barrel `src/server/commerce/index.ts` ALSO re-exports the new (`getCommerceServerRepositoryDb`, `commerceReadRepositoryKysely` + its interface) and KEEPS the old re-exports (`getCommerceServerRepository`, `commerceReadRepository`, `CommerceReadRepository`, `CommerceServerRepository`, and the `COMMERCE_SCHEMA, withTenant` line: CM-13 owns removing those, not this spec).
- Isolation spec (the compliance crown jewel), `.itest.ts` (Docker, TRUST AUTH): `src/server/commerce/repository/__tests__/read.isolation.spec.ts`. `migratePublic` + `provisionTenant(TG_A)` + `provisionTenant(TG_B)`; seed DISTINCT data per schema; plant a same-named `public.product` DECOY. Run the NEW `commerceReadRepositoryKysely` (or `getCommerceServerRepositoryDb`) scoped via `commerceTenantDb(TG_A)` and assert: TG_A sees only TG_A (zero TG_B, zero decoy); a TG_B handle returns ZERO for a TG_A product/variant id (schema wall); symmetry; the GRANT PROOF (a `commerce_app`-scoped connection to tg_a reading tg_b raises `permission denied for schema`). PLUS a structural test (compile-time + runtime shape assertion) that `getCommerceServerRepositoryDb(commerceTenantDb(tg))` satisfies `CommerceServerRepository`. Test the NEW path, not the old.
- Keep the existing `read.test.ts` unit coverage green WITHOUT porting it (the old path is untouched, so it still passes as-is). If you add unit coverage for the new path, add it; do not reduce the existing assertions.
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass (they will: `page.tsx` still calls the intact two-arg old factory, so nothing is broken). Single conventional commit e.g. `feat(commerce): Kysely read repo + getCommerceServerRepositoryDb alongside Prisma (expand) + isolation spec (CM-07)`.

## Constraints

- EXPAND ONLY. Add the new Kysely read funcs + `getCommerceServerRepositoryDb` + the new barrel exports; do NOT modify the existing `commerceReadRepository`, the existing `getCommerceServerRepository`, the `CommerceServerRepository` interface in `hydrateBindings.ts`, or ANY caller (`page.tsx`, the API routes, existing tests). If you find yourself editing a call site or an existing signature, STOP, that is CM-10/CM-13 work.
- Files you may touch: `src/server/commerce/repository/read.ts` (add), the barrel `src/server/commerce/index.ts` (add new exports, keep old), and the new `read.isolation.spec.ts`. Nothing else. Do NOT touch `catalog.ts`/`pricing.ts` (CM-06), `reserve.ts` (CM-08), `order.ts`/`createOrder.ts` (CM-09), `repository/types.ts`, `page.tsx`/routes (CM-10), `hydrateBindings.ts`, the migrations, Prisma, or `withTenant.ts`.
- The advisory `getAvailability` contract is reads-only and display-only: an availability value is NEVER permission to sell. A missing/soft-deleted variant still throws (the hydrator swallows it into an empty slot); a SKU with no live inventory item is availability 0. Preserve that exactly in the new path.
- New Kysely interface types live co-located in `read.ts`, NOT in `repository/types.ts` (keeps this spec off the file CM-09 touches).
- Isolation tests use the container's TRUST auth (`POSTGRES_HOST_AUTH_METHOD: 'trust'` + username-only `postgresql://role@host` URIs, NO password literals: hardcoded passwords trip GitGuardian and block the PR). Squash any test-cred history before it lands if it slips in.
- Do not push to any remote. Output a final completion message: the new function/object names you added, confirmation the old Prisma path + `page.tsx` are untouched (so the render path still compiles), and that the isolation + grant-denied + `CommerceServerRepository`-satisfaction proofs pass against the NEW path.

## Notes

- WHY expand-contract here specifically fixes the v1 hazard: the v1 CM-07 retyped `getCommerceServerRepository` in place, which broke `page.tsx` at typecheck and forced a "leave the route broken, hand it to CM-10" note. Adding a SECOND factory removes that entirely: the old two-arg factory stays, `page.tsx` compiles, and CM-10 does a clean caller flip. Do not try to make it a clean in-place replace.
- `jsonArrayFrom` is the idiomatic way to reproduce a Prisma `include` graph in one query; verify the exact import path + signature against the installed kysely version. Diff the new mapper output against the existing `read.test.ts` expectations so the DTO shape matches field-for-field.
- `available_quantity` / `option_signature` are `Generated<>` (CM-05): the new `getAvailability` reads `available_quantity` directly; never INSERT/UPDATE it.
- The new funcs carry a temporary suffix (`Kysely` / `Db`) so they coexist with the old. CM-13 renames them to canonical (`getCommerceServerRepositoryDb` -> `getCommerceServerRepository`) once the old path is deleted, and updates the CM-10 callers. Leave the suffix in place here.
- The isolation `.itest.ts` runs under CI (`pnpm test:integration`), excluded from the in-loop unit `pnpm test`. The `CommerceServerRepository`-satisfaction guarantee is compile-time, so the in-loop `tsc` enforces it. If Docker is local, run `pnpm test:integration -t isolation` to self-verify.
