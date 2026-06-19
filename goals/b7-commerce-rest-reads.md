---
task: b7-commerce-rest-reads
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b7-commerce-rest-reads.md
depends_on: ["b4-catalog-schema","b3-guarded-reservation","b5-pricing-and-tax"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce REST read surface (b7, commerce-engine track, wave 2)

This is part of the framer-clone build (build-2026-06, commerce-engine track). Build EXACTLY the b7-commerce-rest-reads spec, nothing more, nothing from other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b7-commerce-rest-reads.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Expose `/api/commerce/*` GET read routes following the Track-0 api conventions plus b1 `withTenant`, with reads UNAUTHENTICATED for the v1 cut.
- `src/app/api/commerce/products/route.ts` (GET list, returns `{ products: ProductDTO[]; nextCursor?: string }`) and `src/app/api/commerce/products/[handle]/route.ts` (GET detail by handle, `ProductDTO` or 404), resolving the typed commerce graph via the b4 CatalogRepository plus the b5 resolved price.
- `src/app/api/commerce/inventory/route.ts` (GET `available_quantity` by `variantId` plus `locationId`, returns `AvailabilityDTO`) reading via the b2/b3 inventory repo.
- `src/lib/commerce/dto.ts` with `ProductDTO` (id, handle, title, description, options, variants, `resolvedPriceCents`) and `AvailabilityDTO` (variantId, locationId, `availableQuantity`, `advisoryOnly: true`). Validate route responses with zod.
- CRITICAL semantics: the exposed `available_quantity` is ADVISORY-ONLY (fire-and-forget freshness). Type it and comment it as advisory-only with a citation to the doc. NO client path may treat a read availability number as permission to complete a sale: the b3 guarded reserve is the SOLE authority and rejects at reserve time regardless.
- The commerce DTOs are a parallel read surface: do NOT force the rich commerce graph through the flat CMS Collection/Row shape (it shares nothing in the DB with the CMS tier).
- Integration tests under `src/app/api/commerce/__tests__/*.itest.ts`: list returns the typed graph (not a flat CMS Row), detail resolves by handle, inventory matches the b2 generated column, the DTO carries the advisory-only marker, and reads are unauthenticated.
- REQUIRED headless coverage (do NOT skip): also add `*.test.ts` unit tests that run under the HEADLESS `pnpm test` node project (Docker-free, with a mocked/fake CatalogRepository + inventory repo and canned rows), covering the DTO mapping (commerce graph -> ProductDTO/AvailabilityDTO), the zod response validation, the advisory-only marker, and each route's error envelope (invalid input, 404 not-found). RATIONALE: the verify gate is `pnpm test`, and the vitest config EXCLUDES `.itest.ts` (those only run under the Docker-backed `pnpm test:integration`). Without a headless `.test.ts`, a green gate proves NOTHING about b7 (this exact hollow-gate hole was caught in b5 and b6). Mirror `pricing.test.ts` / `createOrder.test.ts`.

## Hard constraints (do NOT)

- This is a RESOLVER/route spec: keep all new code React-free and Node-evaluable (route handlers, DTOs, zod schemas only). Do NOT add UI.
- ADD NO models to `prisma/schema.prisma`. This spec adds API route handlers plus DTOs only and declares `sharedState: []`. Do NOT touch the `prisma-schema` shared state owned by the b2-b6 schema specs, and do NOT run any prisma writer here.
- Do NOT build other specs' surface: NO order-mutation route (E8 checkout; Track C posts to it), NO authoritative broadcast (E6), NO Yjs/CRDT (E5), NO realtime transport. Reads are plain REST/polling for the v1 cut.
- Do NOT touch MST or the `mst-tree` shared state. Do NOT touch shared state owned by another spec beyond this spec's declared `sharedState` (which is empty). Keep changes minimal and confined to the files in the spec's Files-and-changes table.
- Do NOT provision infrastructure (no Coolify, no real Postgres, no DNS). Routes need only a placeholder `DATABASE_URL` at build (headless verify); the lazy Track-0 prisma singleton makes `next build` pass headless.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges at Gate B.
- Errors must surface, never be swallowed: a failed read or invalid input returns a real error envelope, not a silent success or a swallowed exception.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section (the 3 GET routes through `withTenant` returning zod-validated typed commerce DTOs unauthenticated; `resolvedPriceCents` via b5; advisory-only availability typed, commented, and integration-asserted against the generated column; no broadcast, no Yjs, no order-mutation route; STATUS row flipped). Final gate (also the in-loop verify): `DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
