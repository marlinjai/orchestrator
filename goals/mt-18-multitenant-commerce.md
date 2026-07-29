---
task: mt-18
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-13, mt-14]
shared_state: [prisma, migrations]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **MT-18** (section "MT-18 - Multi-tenant commerce"): make commerce isolation per-tenant via a per-tenant Postgres SCHEMA (decision D6), reusing the `withTenant` `SET LOCAL search_path` seam. Today all commerce runs in ONE shared `commerce` schema, so a multi-tenant storefront with commerce would share one catalog + order ledger across all tenants. This GATES multi-tenant COMMERCE only — CMS-only multi-tenant sites already ship without it.

## Read first

- The MT-18 section + the "Recommended approach (ONE, with rationale)" in `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`, and decision D6.
- `src/server/commerce/withTenant.ts`: `withTenant(prisma, schema, fn)` already takes an explicit allowlisted schema and issues `SET LOCAL search_path TO "<schema>"`. `COMMERCE_SCHEMA = 'commerce'`. `assertSafeSchema` allowlist regex.
- `src/server/commerce/tenant.ts` (landed by MT-13): `resolveCommerceSchemaForSite(site)` — the SEAM. It returns `COMMERCE_SCHEMA` for all sites today. MT-18 replaces its body with a per-tenant registry lookup, WITHOUT changing its callers.
- `src/server/commerce/repository/read.ts`: `getCommerceServerRepository(prisma, schema = COMMERCE_SCHEMA)` (MT-13 added the schema param) threads `schema` into `withTenant`.
- THE TWO HAND-ROLLED `SET LOCAL` SITES that bypass `withTenant` (they open their own `prisma.$transaction` for READ COMMITTED): `src/server/commerce/order/createOrder.ts:~289` (runOrderTransaction) and `~435` (resolvePriorOrder). Both hand-issue `SET LOCAL search_path TO "${COMMERCE_SCHEMA}"`. MT-18 MUST thread the resolved tenant schema into BOTH, not just `withTenant`.
- `src/server/commerce/repository/order.ts:~34`: `ORDER_NUMBER_SEQ = "${COMMERCE_SCHEMA}"."order_number_seq"` — per-tenant schema means a per-tenant sequence (it lives in each tenant schema, created by provisioning).
- `src/server/commerce/inventory/reserve.ts:~136`: `SCHEMA = COMMERCE_SCHEMA` + raw `inventory_level` refs. `src/app/api/commerce/inventory/route.ts:~43`: `LEVEL_TABLE = Prisma.raw("${COMMERCE_SCHEMA}"."inventory_level")`. Both must take the resolved schema.
- `prisma/migrations/` — the commerce migrations (`*_commerce_minimal_orders`, `*_commerce_inventory_ledger`, `*_commerce_catalog`, etc.) contain the commerce DDL incl. RAW-SQL pieces NOT in schema.prisma: `inventory_level.available_quantity GENERATED ALWAYS AS (...) STORED`, `product_variant.option_signature` trigger-maintained column + triggers + partial-unique indexes, and CHECK constraints. A provisioned tenant schema MUST reproduce ALL of these, not just the Prisma-modeled tables.
- `src/server/commerce/inventory/__tests__/schema.itest.ts` + the orders `route.itest.ts` — the existing commerce integration tests (Dockerized Postgres) to mirror for the two-tenant isolation test.

## Definition of done

Recommended approach (per the plan; reuse the `withTenant` seam, do NOT add `workspace_id` columns to the ~14 commerce tables):

1. **Tenant-schema registry**: map a site's tenant (key on `tenantGroupId`) to a Postgres schema name (e.g. a `commerce_<sanitized-tenantGroupId>` deterministic name, recorded in a registry table in the `public` schema, e.g. `CommerceTenantSchema { tenantGroupId @id, schemaName, createdAt }`). Add the Prisma model + a migration. The schema name MUST pass `assertSafeSchema` (allowlisted identifier).

2. **`resolveCommerceSchemaForSite(site)`**: replace the constant return with a registry lookup keyed on `site.tenantGroupId`. If a tenant has no commerce schema yet, either provision it lazily (see 3) or fall back deterministically — but a site that USES commerce must resolve to ITS OWN schema, never the shared one.

3. **Provisioning** (`provisionCommerceSchema(tenantGroupId)`): on first commerce-enable for a tenant, CREATE the schema and run the FULL commerce DDL inside it — every table, the `order_number_seq`, the GENERATED `available_quantity` column, the `option_signature` trigger + triggers, the partial-unique indexes, and the CHECK constraints. Achieve this with an explicit, schema-parameterized DDL TEMPLATE (a single source-controlled `.sql` template applied with the tenant schema substituted) rather than rewriting Prisma migration files at runtime — idempotent (`CREATE ... IF NOT EXISTS` where possible) so it is safe to re-run. Register the tenant in the registry table.

4. **N-schema migration runner**: a documented runner (a script + npm task, e.g. `scripts/migrate-commerce-tenants.ts`) that applies the latest commerce DDL template to ALL registered tenant schemas on deploy. Document it in `deploy/README.md` or a commerce README.

5. **Thread the resolved schema everywhere** the constant `COMMERCE_SCHEMA` is used at runtime: `getCommerceServerRepository` (done via MT-13's param — pass the resolved schema), the TWO hand-rolled `SET LOCAL` sites in `createOrder.ts`, `reserve.ts`, and the inventory route. `grep` must show no order/inventory RUNTIME path pinned to the single constant `commerce` schema (the constant may remain as the default / the shared-tenant name).

6. **The shared `commerce` schema** stays as the default for the existing single seeded tenant (so nothing breaks); new tenants get their own provisioned schema.

Acceptance / tests (integration, `.itest.ts`, CI runs them):
- Seed TWO tenants, provision a schema for each, create a product + an order in each, and assert NEITHER tenant can read the other's catalog or order ledger; assert `order_number_seq` is per-tenant (each tenant's order numbers start independently).
- Provisioning reproduces the generated column + trigger + constraints (assert e.g. `available_quantity` is computed and a CHECK rejects oversell in a provisioned tenant schema).

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(commerce): per-tenant schema registry + provisioning + N-schema migration runner (MT-18)`.

## Constraints

- Stay in this worktree. Do NOT add `workspace_id` columns to the commerce entity tables (the chosen approach is schema-per-tenant). Do NOT change the CMS or render tenancy (MT-13 owns the seam you consume).
- The shared `commerce` schema and the single seeded tenant MUST keep working (the existing commerce tests stay green).
- Migration drift guard: when you add the registry-table migration, `prisma migrate dev` may propose DROPping the generated `available_quantity` / `option_signature` columns and the raw triggers/constraints — those are intentionally absent from `schema.prisma`. DELETE any such destructive DROP from the generated migration (this is a known repo gotcha). Verify the migration only ADDs the registry table.
- Do not push to any remote. Output a final completion message. If the schema-template / migration-runner story cannot be made correct + tested within budget, STOP and emit a clear escalation describing exactly what is blocked rather than committing a half-built provisioning path.

## Notes

- This is the single largest unbuilt data concern and the highest-risk spec. Correctness of the per-tenant DDL (generated columns, triggers, sequences, constraints) is the whole point — a provisioned schema that silently omits the `available_quantity` generated column or the oversell CHECK would corrupt inventory. Prove them in the integration test.
- The two hand-rolled `SET LOCAL` sites in `createOrder.ts` are easy to miss — they are NOT `withTenant` calls. Thread the resolved schema into both.
- Multi-tenant COMMERCE go-live is gated here, but CMS-only go-live is NOT — so this spec is allowed to land after the CMS-only cutover. Do not block on it; build it correctly.
