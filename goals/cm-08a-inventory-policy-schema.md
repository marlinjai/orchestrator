---
task: cm-08a
spec: docs/research/2026-06-27-medusa-inventory-backorder-reference.md
depends_on: [cm-05]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Add the **Medusa-style configurable inventory policy** to the per-tenant commerce schema: the `manage_inventory` + `allow_backorder` flags on `product_variant`, and DROP the hard `CHECK (reserved_quantity <= stocked_quantity)` oversell constraint so backorder can reserve beyond stock. This is the SCHEMA groundwork that the reworked reserve heart (CM-08) needs. Money/stock-critical: it relaxes an integrity constraint, so the new tenant migration + its probe test must be exact.

Decided by Marlin 2026-06-27 (see `docs/research/2026-06-27-medusa-inventory-backorder-reference.md`, the grounded Medusa reference): overselling is NOT a hard error; it is per-variant configurable. `manage_inventory` defaults TRUE (our SKU-bridge assumes tracking; a deliberate divergence from Medusa's false). `allow_backorder` defaults FALSE. The oversell guard moves OUT of the DB CHECK and INTO the reserve path's WHERE clause (CM-08), where it applies only to the managed-no-backorder case.

## Read first

- `docs/research/2026-06-27-medusa-inventory-backorder-reference.md` (the model + the truth table + the schema-change recommendation: flags on `product_variant`, DROP the reserved<=stocked CHECK, keep the GENERATED `available_quantity` and let it go negative under backorder, NO `available >= 0` CHECK).
- The shipped (do NOT edit) tenant migrations: `src/server/commerce/migrations/tenant/001_inventory_ledger.ts` (it created `inventory_level` with `available_quantity GENERATED ALWAYS AS (stocked_quantity - reserved_quantity) STORED` and the constraint `inventory_level_reserved_lte_stocked_check` at ~line 120, plus `inventory_level_stocked_nonneg_check` / `inventory_level_reserved_nonneg_check`), `003_catalog.ts` (it created `product_variant`), and the set in `index.ts` (`COMMERCE_TENANT_MIGRATIONS` = 000_enums..005_minimal_orders). You ADD a new migration; you do NOT modify the shipped ones (they are already applied; migrations are append-only and evolve forward).
- `src/server/commerce/db-types.ts` (CM-05): `ProductVariantTable` (~line 229) currently has `id`, `product_id`, `sku`, `barcode`, `option_signature: Generated<string|null>`. You add the two new boolean columns here.
- `src/server/commerce/migrations/tenant/__tests__/provision.itest.ts` (CM-04): it PROBES the constraint you are dropping (asserts `inventory_level_reserved_lte_stocked_check` raises on `reserved > stocked`). That assertion must be UPDATED to the post-006 reality (the constraint is gone; backorder is now allowed).

## Definition of done

- New `src/server/commerce/migrations/tenant/006_inventory_policy.ts` (a tenant-db `Migration` with `id: '006_inventory_policy'`, bare table names, the runner injects `SET LOCAL search_path`):
  - `ALTER TABLE "product_variant" ADD COLUMN IF NOT EXISTS "manage_inventory" boolean NOT NULL DEFAULT true`
  - `ALTER TABLE "product_variant" ADD COLUMN IF NOT EXISTS "allow_backorder" boolean NOT NULL DEFAULT false`
  - `ALTER TABLE "inventory_level" DROP CONSTRAINT IF EXISTS "inventory_level_reserved_lte_stocked_check"`
  - Keep `inventory_level_stocked_nonneg_check` and `inventory_level_reserved_nonneg_check` INTACT (do not drop those: stocked stays >= 0, reserved stays >= 0; only the reserved<=stocked relation is relaxed). The GENERATED `available_quantity` column is unchanged and may now go negative.
- Register the new migration LAST in `src/server/commerce/migrations/tenant/index.ts` (`COMMERCE_TENANT_MIGRATIONS` array, after `005_minimal_orders`), with the import.
- `src/server/commerce/db-types.ts`: add to `ProductVariantTable`: `manage_inventory: Generated<boolean>` and `allow_backorder: Generated<boolean>` (Generated because they carry a DB DEFAULT, so inserts may omit them).
- Update `src/server/commerce/migrations/tenant/__tests__/provision.itest.ts`: replace the assertion that `inventory_level_reserved_lte_stocked_check` raises on `reserved > stocked` with the new reality: (a) the two new `product_variant` columns exist with defaults `manage_inventory=true` / `allow_backorder=false`; (b) the reserved<=stocked CHECK is GONE — an UPDATE pushing `reserved_quantity` ABOVE `stocked_quantity` now SUCCEEDS and `available_quantity` reads NEGATIVE (= backorder depth); (c) `stocked_nonneg` / `reserved_nonneg` still RAISE on negative values. Do NOT weaken unrelated assertions.
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass. Single conventional commit e.g. `feat(commerce): inventory policy flags + drop reserved<=stocked CHECK for backorder (CM-08a)`.

## Constraints

- ADD a new migration `006_inventory_policy.ts`; do NOT edit the shipped 000..005 migration bodies (append-only). Do NOT touch the OLD Prisma path (`prisma/schema.prisma`, the prisma/migrations SQL, the Prisma commerce repos) — the old path keeps its hard-fail behavior and is deleted in CM-13; the flags live only in the tenant (tg_) schema + `CommerceDB` types where the new reserve path (CM-08) consumes them.
- Files you may touch: new `tenant/006_inventory_policy.ts`, `tenant/index.ts` (register), `db-types.ts` (two columns), `tenant/__tests__/provision.itest.ts` (update the constraint probe). Nothing else. Do NOT touch `reserve.ts` (CM-08 owns the reserve-logic branch), the routes, or the repos.
- The migration is per-tenant and idempotent (`ADD COLUMN IF NOT EXISTS`, `DROP CONSTRAINT IF EXISTS`); re-running `provisionTenant` / `migrateAllTenants` must be a no-op once applied.
- Testcontainer probe uses TRUST auth (`POSTGRES_HOST_AUTH_METHOD: 'trust'` + username-only URLs, NO password literals: GitGuardian blocks hardcoded passwords; see CM-04).
- Do not push to any remote. Output a final completion message: the columns added (with defaults), confirmation the reserved<=stocked CHECK is dropped while the non-negative CHECKs remain, and that `available_quantity` is verified to go negative under backorder.

## Notes

- This spec ONLY changes the schema + types + the migration probe. It does NOT change any reserve/checkout behavior yet (reserve.ts still has the old guarded decrement; the new Kysely reserve with the 3-case branch is CM-08). After this lands, a managed-no-backorder variant is still protected because CM-08's reserve WHERE clause re-imposes `(stocked - reserved) >= n` for that case; the DB CHECK is no longer the guard.
- Dropping a CHECK that an earlier migration in the same set created is normal forward migration evolution: `006` drops what `001` added. The provision test runs ALL migrations then probes, so after `006` the constraint is absent by design.
- `available_quantity` going negative is intentional and is the backorder-depth source of truth (per the research doc); do not add a floor or a new column.
