---
task: cm-04-recon
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
companion_of: cm-04
purpose: ground-truth DDL the CM-04 Worker must reproduce per tg_<id> schema
---

# CM-04 recon: the exact commerce DDL to reproduce per `tg_<id>` schema

This is the ground truth for `COMMERCE_TENANT_MIGRATIONS` (`001`..`006`). Every
structure below currently lives in the single physical `commerce` schema, created
by 5 hand-written (never Prisma-generated) migration SQL files. The Worker ports
each body 1:1 into a `@marlinjai/tenant-db` `Migration` `up(tx)` with TWO mechanical
edits and NOTHING else:

1. Strip the `"commerce".` / `commerce.` schema qualifier from every table, type,
   trigger, function, sequence, and index name. Use BARE names. The runner issues
   `SET LOCAL search_path = <tg schema>, ext` before each `up`, so bare names
   resolve to the tenant schema.
2. Qualify the two shared helpers explicitly: column UUID DEFAULTs use
   `ext.gen_uuid_v7()` and updated_at triggers use `ext.touch_updated_at()` (both
   installed by the public `001_ext_schema` migration, CM-03). The SOURCE below
   uses Prisma-style `id TEXT` PKs with app-supplied ids and `updated_at TIMESTAMP(3) NOT NULL`
   without a DB default. Pre-MVP, no back-compat: prefer `id uuid PRIMARY KEY DEFAULT ext.gen_uuid_v7()`
   and `updated_at timestamptz NOT NULL DEFAULT now()` + a `BEFORE UPDATE ... ext.touch_updated_at()`
   trigger to match the tenant-db example set idiom. If you keep `TEXT` ids to
   minimize app-code churn, FLAG it; either way every CHECK / index / FK / trigger
   / sequence / REVOKE below MUST be reproduced byte-for-byte in meaning.

The REVOKEs target `commerce_app` (created by CM-02 `prisma/sql/commerce-roles.sql`).
Inside a provisioned `tg_<id>` schema the app role is a non-owner, so the REVOKEs
have teeth. Keep the `DO $$ ... IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='commerce_app') ... $$`
guard so a migration applied before the role exists does not error.

ORDER constraint: enums and composite-FK target uniques must exist before the
tables/constraints that use them. So enums come FIRST (a `000_enums` or folded into
the head of the earliest migration that needs them), and `product_option_value`'s
`(id, option_id)` unique must exist before the `product_variant_option` composite FK.

---

## The 9 enum types (per-schema, bare names). Exact value sets:

- `StockMovementType`: `('receive', 'reserve', 'release', 'fulfill', 'adjust', 'transfer')`
- `ProductStatus`: `('draft', 'published')`
- `PriceListStatus`: `('draft', 'active')`
- `PriceListType`: `('override', 'sale')`
- `OrderStatus`: `('pending', 'confirmed', 'cancelled')`
- `CustomerType`: `('b2c', 'b2b')`
- `NetOrGross`: `('net', 'gross')`
- `VariantRefSource`: `('none', 'datatable', 'owned')`
- `TaxTreatment`: `('standard', 'reduced', 'zero', 'reverse_charge', 'kleinunternehmer')`

---

## 001_inventory_ledger (from 20260616120000_commerce_inventory_ledger)

Tables: `inventory_item`, `stock_location`, `inventory_level`, `stock_movement`, `reservation`.

`inventory_item`: id PK, sku TEXT NOT NULL, title TEXT, length_mm/width_mm/height_mm/weight_g INTEGER, created_at, updated_at, deleted_at.
`stock_location`: id PK, name TEXT NOT NULL, created_at, updated_at.
`inventory_level`: id PK, inventory_item_id, location_id, stocked_quantity INTEGER NOT NULL DEFAULT 0, reserved_quantity INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 0, created_at, updated_at.
`stock_movement`: id PK, inventory_item_id, location_id, movement_type `StockMovementType` NOT NULL, quantity INTEGER NOT NULL, request_id TEXT NOT NULL, ref_type TEXT, ref_id TEXT, transfer_group_id TEXT, created_at.
`reservation`: id PK, line_item_id TEXT, location_id NOT NULL, quantity INTEGER NOT NULL, request_id TEXT NOT NULL, created_at, updated_at.

GENERATED column (CRITICAL, probe by behavior):
```
ALTER TABLE inventory_level
  ADD COLUMN available_quantity INTEGER NOT NULL
  GENERATED ALWAYS AS (stocked_quantity - reserved_quantity) STORED;
```

CHECKs on `inventory_level`:
- `inventory_level_reserved_lte_stocked_check`: `CHECK (reserved_quantity <= stocked_quantity)`
- `inventory_level_stocked_nonneg_check`: `CHECK (stocked_quantity >= 0)`
- `inventory_level_reserved_nonneg_check`: `CHECK (reserved_quantity >= 0)`

Unique indexes:
- `inventory_level_inventory_item_id_location_id_key` UNIQUE (inventory_item_id, location_id)
- `stock_movement_request_id_key` UNIQUE (request_id)   <- idempotency, load-bearing for CM-08
- `reservation_request_id_key` UNIQUE (request_id)       <- idempotency, load-bearing for CM-08
- `inventory_item_sku_active_key` UNIQUE (sku) WHERE deleted_at IS NULL   <- PARTIAL

Plain index: `stock_movement_inventory_item_id_location_id_idx` (inventory_item_id, location_id).

FKs (all ON DELETE RESTRICT ON UPDATE CASCADE):
- inventory_level.inventory_item_id -> inventory_item(id)
- inventory_level.location_id -> stock_location(id)
- stock_movement.inventory_item_id -> inventory_item(id)
- stock_movement.location_id -> stock_location(id)
- reservation.location_id -> stock_location(id)

REVOKE (append-only ledger): `REVOKE UPDATE, DELETE ON stock_movement FROM commerce_app;` (role-guarded).

## 002_guarded_reservation (from 20260616130000_commerce_guarded_reservation)

Table `fulfillment_location_default`: workspace_id TEXT PK, location_id TEXT NOT NULL, created_at, updated_at.
FK: fulfillment_location_default.location_id -> stock_location(id) ON DELETE RESTRICT ON UPDATE CASCADE.

DEFERRED CONSTRAINT TRIGGER (CRITICAL, probe by behavior at COMMIT). Function body verbatim (bare names):
```
CREATE OR REPLACE FUNCTION assert_transfer_group_balanced()
RETURNS TRIGGER AS $$
DECLARE
    group_total BIGINT;
    group_count INTEGER;
BEGIN
    IF NEW.transfer_group_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT COALESCE(SUM(quantity), 0), COUNT(*)
        INTO group_total, group_count
        FROM stock_movement
        WHERE transfer_group_id = NEW.transfer_group_id;
    IF group_count <> 2 OR group_total <> 0 THEN
        RAISE EXCEPTION
            'transfer group % is unbalanced: % rows summing to % (expected exactly 2 rows summing to 0)',
            NEW.transfer_group_id, group_count, group_total
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER stock_movement_transfer_balance
    AFTER INSERT ON stock_movement
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION assert_transfer_group_balanced();
```

## 003_catalog (from 20260616140000_commerce_catalog)

Tables: `product`, `product_option`, `product_option_value`, `product_variant`, `product_variant_option`.

`product`: id PK, title NOT NULL, handle NOT NULL, description, status `ProductStatus` NOT NULL DEFAULT 'draft', created_at, updated_at, deleted_at. (NOTE: `tax_class TEXT` is ADDED in 004; keep that ordering or fold it in if you merge.)
`product_option`: id PK, product_id NOT NULL, title NOT NULL, created_at, updated_at, deleted_at.
`product_option_value`: id PK, option_id NOT NULL, value NOT NULL, created_at, updated_at, deleted_at.
`product_variant`: id PK, product_id NOT NULL, title, sku, barcode, created_at, updated_at, deleted_at. (`option_signature TEXT` ADDED below via trigger column; `tax_class TEXT` ADDED in 004.)
`product_variant_option`: variant_id, option_id, option_value_id; PRIMARY KEY (variant_id, option_id).

Composite-FK TARGET unique (MUST exist before the composite FK):
- `product_option_value_id_option_id_key` UNIQUE (id, option_id)

FKs:
- product_option.product_id -> product(id) ON DELETE CASCADE ON UPDATE CASCADE
- product_option_value.option_id -> product_option(id) ON DELETE CASCADE ON UPDATE CASCADE
- product_variant.product_id -> product(id) ON DELETE CASCADE ON UPDATE CASCADE
- product_variant_option.variant_id -> product_variant(id) ON DELETE CASCADE ON UPDATE CASCADE
- COMPOSITE FK (CRITICAL): product_variant_option(option_value_id, option_id) -> product_option_value(id, option_id) ON DELETE RESTRICT **ON UPDATE RESTRICT** (RESTRICT, not CASCADE: deliberate)

Trigger-maintained column: `ALTER TABLE product_variant ADD COLUMN option_signature TEXT;` (nullable).

BEFORE INS/UPD trigger (bare-variant case) verbatim:
```
CREATE OR REPLACE FUNCTION compute_variant_option_signature()
RETURNS TRIGGER AS $$
DECLARE sig TEXT;
BEGIN
    SELECT string_agg(option_value_id, ',' ORDER BY option_value_id)
        INTO sig FROM product_variant_option WHERE variant_id = NEW.id;
    NEW.option_signature := sig;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER product_variant_option_signature
    BEFORE INSERT OR UPDATE ON product_variant
    FOR EACH ROW EXECUTE FUNCTION compute_variant_option_signature();
```

AFTER INS/UPD/DEL trigger (matrix-authoritative recompute) verbatim:
```
CREATE OR REPLACE FUNCTION refresh_variant_option_signature()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE product_variant
        SET option_signature = (
            SELECT string_agg(option_value_id, ',' ORDER BY option_value_id)
                FROM product_variant_option
                WHERE variant_id = COALESCE(NEW.variant_id, OLD.variant_id)
        )
        WHERE id = COALESCE(NEW.variant_id, OLD.variant_id);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER product_variant_option_signature_matrix
    AFTER INSERT OR UPDATE OR DELETE ON product_variant_option
    FOR EACH ROW EXECUTE FUNCTION refresh_variant_option_signature();
```

The 6 partial-unique indexes (all WHERE deleted_at IS NULL):
- `product_handle_active_key` UNIQUE (handle)
- `product_option_product_id_title_active_key` UNIQUE (product_id, title)
- `product_option_value_option_id_value_active_key` UNIQUE (option_id, value)
- `product_variant_sku_active_key` UNIQUE (sku)
- `product_variant_barcode_active_key` UNIQUE (barcode)
- `product_variant_option_signature_active_key` UNIQUE (option_signature)

## 004_pricing_and_tax (from 20260616150000_commerce_pricing_and_tax)

AlterTable: `product ADD COLUMN tax_class TEXT;` and `product_variant ADD COLUMN tax_class TEXT;` (if you fold tax_class into 003's CREATE TABLE, do it consistently and FLAG it).

Tables: `price_set`, `price`, `price_rule`, `price_list`, `credit_note`, `credit_note_ref`.
`price_set`: id PK, variant_id TEXT (nullable), created_at, updated_at.
`price`: id PK, price_set_id NOT NULL, price_list_id (nullable), currency_code NOT NULL, amount INTEGER NOT NULL, min_quantity INTEGER, max_quantity INTEGER, created_at, updated_at.
`price_rule`: id PK, price_id NOT NULL, attribute NOT NULL, value NOT NULL, operator TEXT NOT NULL DEFAULT 'eq', priority INTEGER NOT NULL DEFAULT 0, created_at, updated_at.
`price_list`: id PK, title, status `PriceListStatus` NOT NULL DEFAULT 'draft', type `PriceListType` NOT NULL DEFAULT 'override', starts_at, ends_at, created_at, updated_at.
`credit_note`: id PK, corrected_ref TEXT, reason TEXT, currency_code NOT NULL, amount INTEGER NOT NULL, created_at. (`order_id TEXT` ADDED in 005.)
`credit_note_ref`: id PK, credit_note_id NOT NULL, ref_type NOT NULL, ref_id NOT NULL, created_at.

Indexes: `price_set_variant_id_key` UNIQUE (variant_id); `price_price_set_id_currency_code_idx` (price_set_id, currency_code); `price_rule_price_id_idx` (price_id); `credit_note_ref_ref_type_ref_id_idx` (ref_type, ref_id).

FKs (all ON DELETE CASCADE ON UPDATE CASCADE): price_set.variant_id -> product_variant(id); price.price_set_id -> price_set(id); price.price_list_id -> price_list(id); price_rule.price_id -> price(id); credit_note_ref.credit_note_id -> credit_note(id).

CHECKs:
- `price_amount_nonneg_check`: `CHECK (amount >= 0)`
- `credit_note_amount_nonneg_check`: `CHECK (amount >= 0)`
- `price_min_quantity_nonneg_check`: `CHECK (min_quantity >= 0)`
- `price_max_quantity_nonneg_check`: `CHECK (max_quantity >= 0)`
- `price_quantity_band_check`: `CHECK (min_quantity <= max_quantity)`
- `price_currency_code_iso4217_check`: `CHECK (currency_code ~ '^[A-Z]{3}$')`
- `credit_note_currency_code_iso4217_check`: `CHECK (currency_code ~ '^[A-Z]{3}$')`

REVOKE: `REVOKE UPDATE, DELETE ON credit_note FROM commerce_app;` and `REVOKE UPDATE, DELETE ON credit_note_ref FROM commerce_app;` (role-guarded).

## 005_minimal_orders (from 20260616160000_commerce_minimal_orders)

Per-schema SEQUENCE: `CREATE SEQUENCE order_number_seq;` (now one per tg schema; CM-09 reads it via `tenantSchemaRef`).

AlterTable: `credit_note ADD COLUMN order_id TEXT;`

Tables: `order` (quoted: it is a reserved word, keep it quoted as `"order"` in raw, or rely on identifier-mode quoting), `order_line_item`.
`order`: id PK, order_number NOT NULL, request_id NOT NULL, status `OrderStatus` NOT NULL DEFAULT 'confirmed', currency_code NOT NULL, tax_region NOT NULL, vat_id, customer_type `CustomerType` NOT NULL DEFAULT 'b2c', reverse_charge BOOLEAN NOT NULL DEFAULT false, net_or_gross `NetOrGross` NOT NULL DEFAULT 'net', kleinunternehmer BOOLEAN NOT NULL DEFAULT false, tax_note TEXT, subtotal INTEGER NOT NULL, tax_amount INTEGER NOT NULL, total INTEGER NOT NULL, created_at, updated_at.
`order_line_item`: id PK, order_id NOT NULL, variant_title, variant_sku, unit_price INTEGER NOT NULL, quantity INTEGER NOT NULL, subtotal INTEGER NOT NULL, tax_class TEXT, tax_rate INTEGER NOT NULL, tax_amount INTEGER NOT NULL, tax_treatment `TaxTreatment` NOT NULL, variant_ref TEXT, variant_ref_source `VariantRefSource` NOT NULL DEFAULT 'none', created_at.

Indexes: `order_order_number_key` UNIQUE (order_number); `order_request_id_key` UNIQUE (request_id) <- load-bearing for CM-09; `order_line_item_order_id_idx` (order_id); `credit_note_order_id_idx` (order_id).

FKs: order_line_item.order_id -> order(id) ON DELETE CASCADE ON UPDATE CASCADE; credit_note.order_id -> order(id) ON DELETE RESTRICT ON UPDATE CASCADE.

CHECKs (CRITICAL: includes the accounting identity):
- `order_subtotal_nonneg_check`: `CHECK (subtotal >= 0)`
- `order_tax_amount_nonneg_check`: `CHECK (tax_amount >= 0)`
- `order_total_nonneg_check`: `CHECK (total >= 0)`
- `order_currency_code_iso4217_check`: `CHECK (currency_code ~ '^[A-Z]{3}$')`
- `order_total_sum_check`: `CHECK (total = subtotal + tax_amount)`   <- the accounting identity
- `order_line_item_unit_price_nonneg_check`: `CHECK (unit_price >= 0)`
- `order_line_item_subtotal_nonneg_check`: `CHECK (subtotal >= 0)`
- `order_line_item_tax_amount_nonneg_check`: `CHECK (tax_amount >= 0)`
- `order_line_item_tax_rate_nonneg_check`: `CHECK (tax_rate >= 0)`
- `order_line_item_tax_rate_ceiling_check`: `CHECK (tax_rate <= 10000)`
- `order_line_item_quantity_pos_check`: `CHECK (quantity > 0)`

REVOKE: `REVOKE UPDATE, DELETE ON "order" FROM commerce_app;` and `REVOKE UPDATE, DELETE ON order_line_item FROM commerce_app;` (role-guarded).

---

## Probe-by-behavior checklist (the `.itest.ts` MUST exercise, not just catalog-check)

1. GENERATED `available_quantity`: insert (stocked=10, reserved=3), read back available=7; attempt INSERT/UPDATE of available_quantity directly -> error.
2. `option_signature` BEFORE trigger: insert a variant with matrix rows present -> signature populated, sorted, comma-joined.
3. `option_signature` AFTER/matrix trigger: write product_variant_option rows -> the variant's signature refreshes without touching the variant row; DELETE a matrix row -> signature recomputes.
4. Per-schema `order_number_seq`: two nextval calls increment 1,2 within the schema; a second provisioned schema has an INDEPENDENT series starting at 1.
5. Each CHECK raises on the out-of-range insert (reserved>stocked; negative stocked; negative price.amount; inverted price band; lowercase currency; total != subtotal+tax_amount; tax_rate>10000; quantity<=0).
6. The 6 partial-unique indexes: a duplicate among live rows RAISES; the same duplicate where one row has deleted_at set is ALLOWED.
7. Composite FK ON UPDATE RESTRICT: a product_variant_option whose (option_value_id, option_id) is not a real product_option_value(id, option_id) pair RAISES.
8. Deferred transfer-balance trigger: a lone transfer half (one stock_movement with a transfer_group_id, no mirror) RAISES at COMMIT; a balanced pair (two rows summing to 0) commits.
9. REVOKEs: as `commerce_app` (scoped to the tg schema), an UPDATE or DELETE on stock_movement / credit_note / credit_note_ref / "order" / order_line_item is denied.
10. Idempotence: a second `provisionTenant` for the same tenantGroupId applies nothing new and leaves the schema intact.
