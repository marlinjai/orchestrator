---
task: trackc-commerce-data-source-seam-and-dtos
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-data-source-seam-and-dtos.md
depends_on: ["b4-catalog-schema","b2-inventory-ledger-schema","track0-backend-foundation"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone CommerceDataSource read seam + typed commerce DTOs (Storefront, Wave 2)

This is part of the framer-clone build (build-2026-06, storefront track). Build EXACTLY this spec, nothing more, nothing from other tracks or other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-data-source-seam-and-dtos.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/commerce/context.tsx`: a `CommerceDataSourceContext` (`React.Context<CommerceDataSource | null>`) plus `useCommerceDataSource()`, mirroring `src/lib/bindings/dataSource/context.tsx`. The hook MUST throw loudly outside a provider, exactly like `useDataSource()`.
- `src/lib/commerce/provider.ts`: the `CommerceDataSource` interface, READS ONLY (listProducts, getProduct, getProductByHandle, listVariants, getVariant, getPrices, getAvailability, subscribe). No write/reserve method anywhere on the catalog/stock path.
- `src/lib/commerce/types.ts`: the typed DTOs (`ProductDTO`, `ProductOptionDTO`, `ProductOptionValueDTO`, `ProductVariantDTO` with title/sku/barcode/resolved option_value coordinate, `PriceDTO` as integer cents + currency + tax_class, `AvailabilityDTO` with availableQuantity + locationId + `stale: boolean`).
- `src/lib/commerce/inMemoryCommerceDataSource.ts`: `getSharedInMemoryCommerceDataSource()` test double seeded with a Medusa-shape fixture (1 product, 2 options, 4 variants, prices, inventory levels per location) implementing the full interface, with polling-based `subscribe`.
- Availability is ADVISORY only: surface `inventory_level.available_quantity` as information, never as permission to sell. Track B remains server-authoritative for stock and writes.
- Map Track B catalog/inventory rows to these DTOs inside the provider; never leak Prisma types to the client.
- `src/lib/commerce/__tests__/inMemoryCommerceDataSource.test.ts`: a contract suite covering listProducts/getProduct/listVariants/getVariant/getAvailability/getPrices + subscribe polling, the hook throwing outside a provider, and an assertion that NO catalog/stock write method exists on the interface.

## Hard constraints (do NOT)

- Resolver-style code: keep this seam React-free where the spec says so. The interface (`provider.ts`), DTOs (`types.ts`), and the in-memory double (`inMemoryCommerceDataSource.ts`) must be Node-evaluable and free of React imports; only `context.tsx` and its hook carry React. The new node-target files live under `src/lib/commerce/**`, which the existing vitest `projects` config routes to the node environment.
- Do NOT add the HTTP provider or any `/api/commerce/*` routes (next spec; Track B `b7-commerce-rest-reads` owns the routes). Do NOT add any write/reserve method (Track B authoritative).
- Do NOT touch `prisma/schema.prisma`. Track B commerce schema specs (`b2-inventory-ledger-schema`, `b4-catalog-schema`, and siblings b2 through b6) append to the SAME `prisma/schema.prisma` serially and must not run concurrently with another prisma writer. This spec is a read-only DTO seam: it consumes those models via the provider mapping but writes NO schema.
- Do NOT touch the existing `DataSourceProvider` / `useDataSource()` CMS seam. This adds a SECOND parallel seam alongside it; the existing seam stays unchanged and `InMemoryDataSourceProvider` stays the active CMS client provider.
- Do NOT touch the MST tree (`mst-tree` shared state). This spec declares an empty `sharedState` and adds NO new MST surface.
- Keep changes minimal and confined to `src/lib/commerce/**`. Do not build other specs' surface, and do not touch shared state owned by another spec beyond this spec's declared `sharedState` (which is empty).
- Errors must surface, never be swallowed: the hook throws loudly outside a provider; the in-memory double must not silently return success on a missing record.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: context, hook, interface, typed DTOs, and in-memory double land; the contract suite is green; the hook throws outside a provider; no write method on the interface. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
