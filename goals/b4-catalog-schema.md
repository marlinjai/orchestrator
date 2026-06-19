---
task: b4-catalog-schema
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b4-catalog-schema.md
depends_on: ["b3-guarded-reservation"]
shared_state: ["prisma","migrations"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone owned catalog schema (commerce-engine, b4-catalog-schema)

This is part of the framer-clone build (build-2026-06, commerce-engine track, wave 2). Build EXACTLY the b4-catalog-schema spec, nothing more, nothing from other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b4-catalog-schema.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Add 5 typed catalog models to `prisma/schema.prisma`: `product` (title/handle/description/status enum draft|published; partial-unique handle WHERE deleted_at IS NULL), `product_option` (title; belongsTo product; unique (product_id, title) on live rows), `product_option_value` (value; belongsTo option; unique (option_id, value) on live rows PLUS a UNIQUE (id, option_id) to serve as the composite-FK target).
- `product_variant` (title/sku/barcode; belongsTo product; partial-unique sku and barcode on live rows; `option_signature` with a DB-enforced UNIQUE).
- `product_variant_option` (the variant<->option_value matrix) with the composite FK `(option_value_id, option_id) -> product_option_value(id, option_id)` so the DB REJECTS a wrong option_id (must-fix 1).
- A raw-SQL migration adds the BEFORE INSERT/UPDATE `option_signature` trigger that recomputes the signature by sorting the variant's option_value_ids from `product_variant_option` (must-fix 2: no two variants can share an option combination).
- `src/server/commerce/repository/catalog.ts`: implement the b1 `CatalogRepository` read/write interface (createProduct/addOption/addOptionValue/addVariant/setVariantOptions, all take a `tx`).
- `src/server/commerce/repository/__tests__/catalog.itest.ts`: integration assertions for composite-FK rejection on mismatched option_id, option_signature collision on identical option-value combinations, signature recompute on edit, and a soft-deleted handle freeing the partial-unique.
- Catalog CONTENT only: NO price (b5), NO inventory linkage (b2/b3), NO Yjs (deferred E5).

## Hard constraints (do NOT)

- This spec TOUCHES SHARED STATE: it appends to the SAME `prisma/schema.prisma` and adds a `prisma/migrations/**` migration. The commerce schema writers b2 -> b3 -> b4 -> b5 -> b6 form a strict serial chain by design; b4's `depends_on: ["b3-guarded-reservation"]` is a serialization edge on the shared schema, not a logical dependency on b3's reserve code. Do NOT run concurrently with another prisma writer. Edit `schema.prisma` minimally: ADD the 5 catalog models + composite FK + UNIQUE FK target only; do NOT rewrite or reorder models another spec owns.
- Do NOT build other specs' surface: NO price / sku-as-money (b5 owns it), NO inventory linkage (b2/b3 own it), NO Yjs binding (E5 owns it). Do NOT touch the `mst-tree` shared state (this is a server-side prisma + repository spec, not an MST-write spec; add no new MST surface).
- The repository at `src/server/commerce/repository/catalog.ts` must stay React-free and Node-evaluable (server-only). Implement the b1 `CatalogRepository` interface over the passed `tx`; do NOT invent a new interface.
- Keep changes minimal and inside this spec's declared sharedState (`prisma`, `migrations`); do NOT touch shared state owned by another spec.
- Do NOT provision infrastructure (no Coolify, no real Postgres, no DNS). Document the `DATABASE_URL` contract only.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges at Gate B.
- Errors must surface, never be swallowed: a failed migration, a rejected composite FK, or a signature collision must throw / fail loudly, never be caught-and-ignored.
- `next build` MUST pass headless with a placeholder `DATABASE_URL` (the singleton is lazy). `pnpm test` stays unit-only; the catalog integration tests (`*.itest.ts`) live behind `pnpm test:integration` and must NOT run in the headless `pnpm test`.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section (the 5 catalog models with their partial-uniques + UNIQUE FK target + option_signature UNIQUE, the composite FK, the raw-SQL option_signature trigger migration, `prisma generate` + migration apply succeeding, the 4 integration assertions passing, and the b1 `CatalogRepository` impl over `tx`). Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
