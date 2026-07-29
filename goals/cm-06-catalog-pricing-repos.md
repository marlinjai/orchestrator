---
task: cm-06
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
depends_on: [cm-05]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **CM-06** (section "### CM-06 — Catalog + pricing read repos → Kysely" of `docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md`, §5.1 catalog/pricing rows + §6 isolation test), using the **EXPAND-CONTRACT (parallel-change) strategy Marlin decided 2026-06-27**.

**Read this framing first, it changes the whole shape of the spec:** the framer-clone verify gate is a WHOLE-PROGRAM typecheck (`tsc --noEmit` + `next build`). If you RETYPE the existing `catalogRepository` / `pricingRepository` method signatures from Prisma `tx` to Kysely `db` in place, you instantly break their callers (`createOrder.ts:307`, `products/route.ts:80`, `products/[handle]/route.ts:51`, `routes.itest.ts`), which are owned by CM-09/CM-10 and out of scope here, and the verify gate fails. So you do NOT replace in place. You ADD the new Kysely path ALONGSIDE the untouched old Prisma path. This matches plan §10 ("the old Prisma path is kept intact through CM-12"). CM-10 flips callers to the new path; CM-13 deletes the old path. This spec is the EXPAND step for catalog + pricing.

## Read first

- The plan's CM-06 section + §5.1 (the per-method Kysely mapping for catalog + pricing) + §6 (the isolation test: TG_A/TG_B + public decoy + grant-denied probe). Plus `~/software-dev/orchestrator/goals/cm-04-recon.md` for the exact catalog DDL (option_signature is trigger-maintained, the composite FK + AFTER trigger are authoritative).
- The source you read but do NOT modify: `src/server/commerce/repository/catalog.ts` (`catalogRepository`, tx-first), `src/server/commerce/repository/pricing.ts` (`pricingRepository` + `assertIntegerCents` + the JS tie-break logic in `resolvePrice`), and `src/server/commerce/repository/types.ts` (`CatalogRepository`/`PricingRepository` interfaces). These STAY as-is so existing callers keep compiling.
- The typed handle + shape: CM-05's `src/server/commerce/db-types.ts` (`CommerceDB`), `src/server/commerce/db.ts` (`commerceTenantDb`, re-exported `tenantDb`, `CommerceDB`), and `@marlinjai/tenant-db` (`tenantDb`, `tenantSchemaRef`).
- The isolation-test template: `auth-brain/packages/tenant-db/src/tests/isolation.spec.ts`; the container/provision/TRUST-AUTH setup in CM-04's `src/server/commerce/migrations/tenant/__tests__/provision.itest.ts`.

## Definition of done (EXPAND: add new, keep old)

- NEW Kysely catalog functions added ALONGSIDE the old object. Add a new exported object (suggested name `catalogRepositoryKysely`, or co-located standalone functions) in `catalog.ts` whose methods take `(db: Kysely<CommerceDB>, args)`: `createProduct/addOption/addOptionValue/addVariant/setVariantOptions/count` mapped per §5.1 (`db.insertInto(...).values(...).returningAll().executeTakeFirstOrThrow()`; `addVariant` OMITS `option_signature` (Generated, trigger owns it); `setVariantOptions` = `deleteFrom(...).where('variant_id','=',id)` then bulk `insertInto(...).values(rows)`, composite FK + AFTER trigger authoritative, no JS re-check; `count` = `selectFrom('product').select(db.fn.countAll()...)`). Multi-statement methods use `db.transaction().execute(...)`. Type the new object with a NEW interface co-located IN `catalog.ts` (do NOT edit `repository/types.ts` — that avoids the CM-08/CM-09 collision on that file).
- NEW Kysely pricing functions added in `pricing.ts` (suggested `pricingRepositoryKysely`): `createPriceSet/addPrice` as structured inserts AFTER the `assertIntegerCents` guard (re-use the existing guard fn, do not duplicate or weaken it); `resolvePrice` as `selectFrom('price_set')...` + `selectFrom('price').leftJoin('price_list',...)` with ALL tie-break/band/window logic kept in JS, INTEGER compares only, returning the stored Int amount or `null`. Behavior must match the old `resolvePrice` exactly (same winning price).
- The OLD `catalogRepository` / `pricingRepository` and the `CatalogRepository`/`PricingRepository` interfaces in `types.ts` are LEFT UNTOUCHED. No existing caller changes. (Sanity: after your change, `git diff` shows `catalog.ts`/`pricing.ts` as ADDITIONS, not signature rewrites of the existing exports.)
- Isolation specs (the compliance crown jewel), `.itest.ts` (Docker, TRUST AUTH): `src/server/commerce/repository/__tests__/catalog.isolation.spec.ts` + `pricing.isolation.spec.ts`. `migratePublic` + `provisionTenant(TG_A)` + `provisionTenant(TG_B)`; seed DISTINCT data per schema; plant a same-named `public.product`/`public.price` DECOY. Run the NEW `catalogRepositoryKysely`/`pricingRepositoryKysely` scoped via `commerceTenantDb(TG_A)` and assert: TG_A sees only TG_A (zero TG_B, zero decoy); a TG_B handle returns ZERO for a TG_A id (schema wall); symmetry; and the GRANT PROOF (a `commerce_app`-scoped connection to tg_a reading tg_b raises `permission denied for schema`). Test the NEW path, not the old.
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass (they will, because no caller is broken: the old path is intact). Single conventional commit e.g. `feat(commerce): Kysely catalog + pricing repos alongside Prisma (expand) + isolation specs (CM-06)`.

## Constraints

- EXPAND ONLY. Add new Kysely functions; do NOT modify the existing `catalogRepository`/`pricingRepository` exports, the `CatalogRepository`/`PricingRepository` interfaces, `repository/types.ts`, or ANY caller (routes, `createOrder.ts`, existing tests). If you find yourself editing a call site or an existing signature, STOP, that is CM-10/CM-13 work.
- Files you may touch: `src/server/commerce/repository/catalog.ts` (add), `pricing.ts` (add), and the two NEW isolation `.itest.ts`. Nothing else. Do NOT touch `read.ts` (CM-07), `reserve.ts` (CM-08), `order.ts`/`createOrder.ts` (CM-09), the barrel `index.ts`, the migrations, Prisma, or `withTenant.ts`.
- Money stays server-authoritative integer cents: re-use `assertIntegerCents`; `resolvePrice` does NO float math; integer compares only.
- New Kysely interface types live co-located in the repo file, NOT in `repository/types.ts` (keeps this spec off the file CM-08/CM-09 touch).
- Isolation tests use the container's TRUST auth (`POSTGRES_HOST_AUTH_METHOD: 'trust'` + username-only `postgresql://role@host`, NO password literals — hardcoded passwords trip GitGuardian and block the PR, see CM-04). Squash any test-cred history before it lands if it slips in.
- Do not push to any remote. Output a final completion message: the new function names you added, confirmation the old Prisma path is untouched (so callers still compile), and that the isolation + grant-denied proofs pass against the NEW path.

## Notes

- WHY expand-contract: the new path is "dark" (no caller yet) until CM-10 flips routes/render to it; the old Prisma path keeps the demo working throughout; CM-13 deletes the old path once nothing calls it. This keeps every merge compile-clean on a whole-program typecheck. Do not try to make it a clean in-place replace, that is the failure mode this strategy exists to avoid.
- `option_signature` / `available_quantity` are `Generated<>`: never INSERT/UPDATE them. The catalog triggers (CM-04) maintain `option_signature` on `setVariantOptions`/`addVariant`.
- The isolation specs run under `pnpm test:integration` (CI Docker), excluded from the in-loop unit `pnpm test`. In-loop verify is unit+build; the isolation proof is the CI gate. If Docker is local, run `pnpm test:integration -t isolation` to self-verify.
