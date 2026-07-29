---
task: cm-04
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
depends_on: [cm-03]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **CM-04** (section "### CM-04 — Commerce per-tenant migration set (HIGH RISK, isolate)" of `docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md`, plus §4.2 "The commerce DDL as per-tenant migrations"). Author `COMMERCE_TENANT_MIGRATIONS` (`001_inventory_ledger` .. `006_enums`) as a `@marlinjai/tenant-db` `MigrationSet` that reproduces EVERY structural guarantee of the existing commerce schema, per `tg_<id>` schema, with BARE table names. This is the structural heart of the migration: every per-tenant schema must be byte-for-byte structurally identical to today's single `commerce` schema, so a wrong filter cannot reach another tenant and `pg_dump -n tg_x` extracts one self-contained customer.

THIS IS THE HIGHEST-RISK SPEC. A missing CHECK, trigger, GENERATED column, partial-unique index, composite FK, or REVOKE is a silent data-integrity or money/stock hole. The `.itest.ts` must PROBE every structure; do not assume, assert.

## Read first (the port source + the target shape)

- The plan's CM-04 section + §4.2 (the per-migration table that enumerates exactly what each of `001`..`006` carries) + §5.3 (GENERATED / trigger / sequence columns). The §4.2 table is your checklist; every row is a probe assertion.
- The EXACT DDL to port (hand-written, never Prisma-generated, so this ports 1:1) lives in framer-clone `prisma/migrations/`:
  - `20260616120000_commerce_inventory_ledger/migration.sql` -> `001_inventory_ledger`
  - `20260616130000_commerce_guarded_reservation/migration.sql` -> `002_guarded_reservation`
  - `20260616140000_commerce_catalog/migration.sql` -> `003_catalog`
  - `20260616150000_commerce_pricing_and_tax/migration.sql` -> `004_pricing_and_tax`
  - `20260616160000_commerce_minimal_orders/migration.sql` -> `005_minimal_orders`
  Read ALL of these in full. They contain the generated column, the deferred transfer-balance trigger + fn, the variant option-signature BEFORE/AFTER triggers + fns, the per-schema sequence, every CHECK, the 6 partial-unique indexes, the composite FK `ON UPDATE RESTRICT`, and the REVOKEs. Port the bodies verbatim except: strip the `commerce.` / `"commerce".` schema qualification (the runner injects `SET LOCAL search_path = <schema>, ext`, so use BARE names), and qualify `ext.gen_uuid_v7()` / `ext.touch_updated_at()` explicitly.
- The target shape: `ERP-suite/projects/lumitra-infra/auth-brain/packages/tenant-db/src/migrations/types.ts` (`Migration = { id: string; up: (tx: TransactionSql) => Promise<void> }`, `MigrationSet = ReadonlyArray<Migration>`) and `src/migrations/tenant/index.ts` (the EXAMPLE set — mirror its structure: each migration a `const` with `id` + `up`, bodies use bare table names, `ext.gen_uuid_v7()` DEFAULTs, `CREATE TRIGGER ... EXECUTE FUNCTION ext.touch_updated_at()`). Your set REPLACES that example's `workspaces/memberships/...` tables with the commerce tables.
- How the set is consumed: `provisionTenant(ownerSql, { tenantGroupId, slug, appRole: 'commerce_app', tenantMigrations: COMMERCE_TENANT_MIGRATIONS })` (runner.ts). The runner wraps each `up` in a tx with the search_path already set. The REVOKEs target `commerce_app` (created by CM-02's `prisma/sql/commerce-roles.sql`); inside a provisioned schema the app role is a non-owner so the REVOKEs have teeth.
- The 9 commerce enum types: today they are Postgres enums in the `commerce` schema. Per §4.2 `006`, create them per-schema (bare names under the injected path): `StockMovementType`, `ProductStatus`, `PriceListStatus`, `PriceListType`, `OrderStatus`, `CustomerType`, `NetOrGross`, `VariantRefSource`, `TaxTreatment`. Read their exact value sets from the source migration SQL (they are defined there); do not invent values.

## Definition of done

- New `src/server/commerce/migrations/tenant/001_inventory_ledger.ts`, `002_guarded_reservation.ts`, `003_catalog.ts`, `004_pricing_and_tax.ts`, `005_minimal_orders.ts`, `006_enums.ts` (or enums inline in `001`/created first; pick what makes the dependency order valid: enums must exist before the tables that use them, so `006_enums` likely must be `000_enums` or folded into the earliest migration — order so every type/table/FK target exists before use). Plus `src/server/commerce/migrations/tenant/index.ts` exporting `COMMERCE_TENANT_MIGRATIONS: MigrationSet` (ordered).
- Every structure from the §4.2 table reproduced per-schema with bare names:
  - `001`: inventory_item, stock_location, inventory_level (incl. `available_quantity INTEGER GENERATED ALWAYS AS (stocked_quantity - reserved_quantity) STORED`), stock_movement; CHECKs (`reserved_quantity <= stocked_quantity`, `stocked_quantity >= 0`, `reserved_quantity >= 0`); partial-unique `inventory_item_sku_active_key WHERE deleted_at IS NULL`; REVOKE UPDATE,DELETE ON stock_movement FROM commerce_app.
  - `002`: reservation, fulfillment_location_default + FK; the DEFERRED CONSTRAINT TRIGGER `stock_movement_transfer_balance` + fn `assert_transfer_group_balanced()`.
  - `003`: product, product_option, product_option_value, product_variant (incl. trigger-maintained `option_signature TEXT`), product_variant_option; the BEFORE INS/UPD trigger + fn `compute_variant_option_signature()`; the AFTER INS/UPD/DEL trigger + fn `refresh_variant_option_signature()`; composite-FK target unique `product_option_value(id, option_id)`; composite FK `product_variant_option(option_value_id, option_id) -> product_option_value(id, option_id) ON UPDATE RESTRICT`; the 6 partial-unique indexes WHERE `deleted_at IS NULL`.
  - `004`: price_set, price, price_rule, price_list, credit_note, credit_note_ref; CHECKs (`price.amount >= 0`, `credit_note.amount >= 0`, min/max-quantity band, `currency_code ~ '^[A-Z]{3}$'`); REVOKE UPDATE,DELETE on credit_note, credit_note_ref.
  - `005`: "order", order_line_item; `CREATE SEQUENCE order_number_seq` (PER-SCHEMA now); CHECKs (money `>= 0`, `currency_code ~ '^[A-Z]{3}$'`, accounting identity `total = subtotal + tax_amount`, line-item `tax_rate <= 10000`, `quantity > 0`); REVOKE UPDATE,DELETE on "order", order_line_item.
  - enums: the 9 types with their real value sets.
- Test `src/server/commerce/migrations/tenant/__tests__/provision.itest.ts` (Testcontainer `postgres:16-alpine`): `migratePublic(owner)` then `provisionTenant(owner, { tenantGroupId: <a uuid>, slug, appRole: 'commerce_app', tenantMigrations: COMMERCE_TENANT_MIGRATIONS })`. Then DIRECT-SQL PROBE the created `tg_<id>` schema for EVERY structure above: the GENERATED column (insert stocked/reserved, read back computed available_quantity), the option_signature triggers FIRING (insert a variant + options, assert signature populated/refreshed), the per-schema `order_number_seq` (nextval increments within schema), each CHECK (an out-of-range insert RAISES), the 6 partial-unique indexes (duplicate-where-not-deleted RAISES, duplicate-where-deleted ALLOWED), the composite FK ON UPDATE RESTRICT, the deferred transfer-balance trigger (an unbalanced transfer group RAISES at COMMIT), and the REVOKEs (an UPDATE/DELETE on an append-only table as commerce_app is denied). Assert re-running provisionTenant is idempotent.
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass. Single conventional commit e.g. `feat(commerce): per-tenant migration set (tg_<id> commerce DDL) (CM-04)`.

## Constraints

- Stay in this worktree. Files: the `migrations/tenant/*.ts` set + index + the provision `.itest.ts` ONLY. Do NOT touch repos/routes/Prisma schema/`src/server/db.ts`/`withTenant.ts`/the public migrations (CM-03). Do NOT yet wire provisionTenant into onboard (CM-11 owns that) — the test calls provisionTenant directly.
- BARE table names in every body (the runner injects the search_path); `ext.gen_uuid_v7()` / `ext.touch_updated_at()` qualified. Do NOT hardcode a `tg_` or `commerce` schema name in any body. Do NOT use `SET search_path` yourself (the runner owns it).
- Port the DDL bodies 1:1 from the source migration SQL — same CHECK expressions, same trigger logic, same index predicates, same FK actions. Do NOT redesign, "improve", or drop any constraint. If the source has something the §4.2 table omits, KEEP it and note it; if §4.2 lists something the source lacks, FLAG the discrepancy in your completion message rather than silently inventing it.
- Order migrations so every enum type, every composite-FK target unique, and every referenced table exists before use. Enums first.
- Do not push to any remote. Output a final completion message that lists, per migration, which structures it carries, and flags ANY source-vs-plan discrepancy you hit.

## Notes

- This removes the Prisma drift hazard entirely (§4.2): no more hand-deleting destructive DROPs from `prisma migrate dev` output. The Kysely/raw runner is the system of record.
- The hardest correctness surface is the trigger/generated-column wiring (option_signature, available_quantity, the deferred transfer-balance constraint). Port those FUNCTION bodies verbatim from the source SQL; they are the parts a probe test must exercise by behavior (insert/update and observe), not just by catalog existence.
- The `.itest.ts` runs under `pnpm test:integration` (CI, Docker), excluded from the unit `pnpm test`. The in-loop verify is unit+build, so structural correctness is gated at CI: the probe test is the real proof. If Docker is available locally, run `pnpm test:integration -t provision` to self-verify before declaring done.
