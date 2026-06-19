---
task: b2-inventory-ledger-schema
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b2-inventory-ledger-schema.md
depends_on: ["b1-commerce-module-skeleton"]
shared_state: ["prisma","migrations"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce inventory ledger schema (b2-inventory-ledger-schema)

This is part of the framer-clone build (build-2026-06, commerce-engine track). Build EXACTLY the b2-inventory-ledger-schema spec, nothing more, nothing from other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b2-inventory-ledger-schema.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Add FIVE owned inventory models to `prisma/schema.prisma` (purpose-built Prisma, NOT data-table): `inventory_item`, `inventory_level`, `stock_movement`, `reservation`, `stock_location`.
- `inventory_item` (iitem): sku, dims, title, with a partial-unique sku WHERE `deleted_at IS NULL` (sku frees on soft-delete).
- `inventory_level` (ilev): `location_id` + `inventory_item_id`; `stocked_quantity` Int + `reserved_quantity` Int; a GENERATED column `available_quantity = stocked_quantity - reserved_quantity` STORED (DB-filterable, written via a raw-SQL migration step because Prisma cannot express generated columns natively); composite `@@unique([inventory_item_id, location_id])`; `version` Int default 0 for optimistic concurrency; a `CHECK (reserved_quantity <= stocked_quantity)` backstop (raw-SQL migration).
- `stock_movement` (smov): APPEND-ONLY ledger and the source of truth (the level is its projection); `inventory_item_id`, `location_id`, `movement_type` enum (receive, reserve, release, fulfill, adjust, transfer), `quantity`, `request_id` UNIQUE, `ref_type`, `ref_id`, nullable `transfer_group_id`, `created_at`.
- `reservation` (resitem): nullable `line_item_id`, `location_id` NOT NULL, `quantity`, `request_id`. `stock_location` (sloc): `name`.
- A migration applies `REVOKE UPDATE,DELETE ON stock_movement FROM commerce_app` (using the b1 role topology) to enforce append-only at the database level.
- Add the integration test `src/server/commerce/inventory/__tests__/schema.itest.ts` covering: generated `available_quantity` auto-updates, CHECK rejects `reserved > stocked`, UPDATE on `stock_movement` as `commerce_app` is DENIED, partial-unique sku frees on soft-delete, `request_id` UNIQUE.

## Hard constraints (do NOT)

- Schema + generated column + append-only REVOKE + CHECK + indexes ONLY. NO write logic, NO reservation guards, NO guarded decrement (those are b3). NO REST reads (b7). Keep changes minimal to exactly this spec's surface.
- This is a `prisma`/`migrations` SHARED-STATE writer. Per the orchestration-loop one-writer-at-a-time rule, the commerce schema specs b2 to b6 APPEND to the SAME `prisma/schema.prisma` SERIALLY: `track0` -> `b1` -> `b2` (this) -> `b3` -> `b4` -> `b5` -> `b6`. Do NOT run concurrently with another prisma writer; this run assumes b1 has already merged. Touch only the `prisma` and `migrations` shared state this spec declares.
- Do NOT touch MST (this spec adds NO MST surface). Do NOT build any other spec's surface (skeleton/role-topology is b1, triggers are b3, catalog is b4, pricing is b5, orders are b6, reads are b7).
- Do NOT provision infrastructure (no Coolify, no real Postgres, no DNS). The integration test runs against Dockerized Postgres only; the headless `pnpm test` (and the verify gate) must pass with the placeholder `DATABASE_URL`.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed. Secrets via Infisical only, never `.env`, never a literal.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section (5 models with composite UNIQUE, CHECK, version, generated `available_quantity` via raw-SQL migration, partial-unique sku, append-only REVOKE; `pnpm exec prisma generate` plus a migration apply against Dockerized Postgres succeed; integration test confirms generated col, CHECK rejection, and the denied UPDATE on stock_movement). Final gate (also the in-loop verify): `DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
