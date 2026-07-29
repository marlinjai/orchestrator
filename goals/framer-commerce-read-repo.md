---
task: framer-commerce-read-repo
spec: docs/specs/build-2026-06/hosted-demo/hosted-page-demo.md
verify: DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Build `getCommerceServerRepository()`: a **read-only, RSC-callable, Prisma-backed** commerce repository
that implements the `CommerceServerRepository` interface the publish hydrator already expects, so the
SSR render layer (a later slice) can bake catalog reads in Node. Today only WRITE / transaction-bound
commerce repos exist (`src/server/commerce/repository/catalog.ts`, `order.ts`, `pricing.ts`,
`withTenant.ts`); this slice adds the missing READ surface. This is build item #3 of the hosted-page
demo plan, reconciled to the P1 foundation.

## The exact interface to satisfy (do NOT invent a new shape)

`src/lib/renderer/publish/hydrateBindings.ts` already declares the contract (type-only) and the demo
plan item #3 names it. Implement these five methods, returning the DTOs from `src/lib/commerce/types.ts`:

```ts
interface CommerceServerRepository {
  listProducts(query?: CommerceQuery): Promise<ProductPage>;            // catalog list -> ProductDTO[] + total (+ nextCursor)
  getProductByHandle(handle: string): Promise<ProductDTO | null>;       // single product by handle, or null
  listVariants(productId: string): Promise<ProductVariantDTO[]>;        // every variant of a product
  getPrices(variantId: string): Promise<PriceDTO[]>;                    // price rows (amountCents = integer minor units)
  getAvailability(variantId: string, locationId?: string): Promise<AvailabilityDTO>; // ADVISORY only
}
```

## Read first

- `src/lib/renderer/publish/hydrateBindings.ts` (the `CommerceServerRepository` interface block +
  the doc comments on what each method must return and the advisory-availability hard line).
- `src/lib/commerce/types.ts` (the DTOs: `ProductDTO`, `ProductVariantDTO`, `PriceDTO`,
  `AvailabilityDTO`, `ProductPage`, `CommerceQuery`, `ALL_LOCATIONS`). Map Prisma rows INTO these;
  never leak `@prisma/client` types past the repo boundary.
- `src/server/commerce/repository/catalog.ts` + `pricing.ts` + `types.ts` (the EXISTING write/read
  query patterns over the `commerce.product` / `product_variant` / `price` / `inventory_level` models;
  reuse their query shapes, tenant-scoping via `withTenant.ts` / `COMMERCE_SCHEMA`, and DTO mappers
  where they already exist — do NOT duplicate a mapper that exists).
- `src/server/commerce/index.ts` (the server-side barrel; add the new read repo export here following
  the existing convention).
- `src/lib/commerce/inMemoryCommerceDataSource.ts` (the in-memory double — a reference for the exact
  DTO shapes and the advisory-availability aggregation semantics the read repo must match).
- `prisma/schema.prisma` (the `commerce` schema models: `product`, `product_option`,
  `product_variant`, `product_variant_option`, `price`, `inventory_level`).

## Definition of done

- `getCommerceServerRepository()` exported from `src/server/commerce/` (server-only), returning an
  object implementing all five methods against real Prisma reads. Tenant scoping consistent with the
  existing commerce repos (workspace/tenant boundary honored on every query).
- `getAvailability` returns the GENERATED `available_quantity` (stocked - reserved) from
  `inventory_level`, aggregated across locations when no `locationId` is given (report
  `locationId: ALL_LOCATIONS`), `stale: false` (fresh DB read). ADVISORY only: never a write, never a
  reservation, never permission to sell. Throws when the variant does not exist (the hydrator's
  documented per-slot swallow turns that into an empty slot).
- `getPrices` returns `amountCents` as integer minor units (the column is an Int; never coerce to
  float). Quantity-band fields (`minQuantity`/`maxQuantity`) mapped when present.
- `listProducts` honors `CommerceQuery` filter/sort/limit (fields: `handle`, `title`) and returns
  `{ products, total, nextCursor? }`. `total` is the count matching the filter, ignoring limit.
- Headless tests (`.test.ts`) for each of the five methods. Per the demo plan test plan: each read
  method against a seeded DB OR a fake returns the expected DTOs. Prefer a fast unit approach
  consistent with how the existing commerce repo tests run in the headless `pnpm test` suite (mock
  Prisma, or use the in-memory pattern); do NOT add a Docker-dependent test to the headless `pnpm test`
  run. If you write a DB-booting proof, use the `.itest.ts` suffix so it runs only under
  `pnpm test:integration`, never in `pnpm test`.
- `DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` all green.
- Single commit, conventional-commit message describing the WHY.

## Constraints

- READS ONLY. There is intentionally NO write / reserve / checkout method on this repo. Server stays
  authoritative for money and stock; this repo is display-read only.
- No `prisma/schema.prisma` changes and no migration (this is a read layer over existing models). If
  you believe a schema change is genuinely required, STOP and escalate rather than editing the schema
  (it would collide with the parallel content-agent slice that holds the prisma lock).
- Do not leak Prisma types past the repo boundary; the public surface is the DTOs only.
- No em-dashes or en-dashes anywhere. Studio conventions; reuse existing mappers/utilities.
- Stay in this worktree. Do not push to any remote (the operator handles PR + merge). Do not run
  destructive commands. When done, output a final completion message listing files changed.

## Notes

- This slice is parallel-safe (no shared_state with the content-agent or CI tasks). It is consumed by
  the later `framer-server-renderer` slice, which depends on it merging first.
- If the existing `httpCommerceDataSource.ts` / `inMemoryCommerceDataSource.ts` already encode the
  filter/sort/availability-aggregation semantics, mirror them exactly so the SSR-baked output matches
  the client storefront's behavior.
