---
task: trackc-commerce-http-provider-and-read-routes
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-http-provider-and-read-routes.md
depends_on: ["trackc-commerce-data-source-seam-and-dtos","b7-commerce-rest-reads"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone HTTP CommerceDataSource provider + read routes (Track C, storefront)

This is part of the framer-clone build (build-2026-06, storefront track, wave 2). Build EXACTLY the trackc-commerce-http-provider-and-read-routes spec, nothing more, nothing from other tracks or other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-http-provider-and-read-routes.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/commerce/httpCommerceDataSource.ts`: `HttpCommerceDataSource implements CommerceDataSource` (the seam from `trackc-commerce-data-source-seam-and-dtos`), calling the Track-B `/api/commerce/*` read routes (catalog list/detail, variants, prices, availability) owned by `b7-commerce-rest-reads`.
- Constructor takes `opts?: { baseUrl?: string; pollMs?: number }`. `subscribe()` polls on an interval (default 5s).
- Map the b7 DTOs to the seam DTOs (or reuse them directly when shape-identical). Surface errors well-formed; NEVER leak Prisma errors out of the provider.
- The availability read carries the HARD LINE: the returned number is advisory-only and NEVER permission to complete a sale (the b3 guarded reserve is the sole authority). The availability shape carries `availableQuantity` + `locationId` + `stale` + the advisory-only marker.
- `src/lib/commerce/__tests__/httpCommerceDataSource.test.ts`: the SAME contract suite that `InMemoryCommerceDataSource` passes, with `fetch` mocked against the b7 route shapes. Add a test asserting no write/reserve happens on the read path, and that errors are well-formed.
- b7 currently exposes `products` (list), `products/[handle]` (detail), `inventory` (availability). If the seam needs `products/[id]/variants` and `variants/[id]/prices` as separate routes, request them as a small additive PR to b7 (Track B owns the route files). Do NOT add route files in this storefront spec.

## Hard constraints (do NOT)

- Do NOT add or own any route handlers. Track B (`b7-commerce-rest-reads`) owns every `/api/commerce/*` route file. This spec adds only the client-side HTTP provider plus its test. `touchesSharedState` is false: no route files here, no new deps here.
- Do NOT build any write/checkout route or post to an order route (that is E8, the checkout spec). This is read-only.
- Do NOT build other specs' surface: not the seam/DTOs (`trackc-commerce-data-source-seam-and-dtos` owns the interface), not the b7 routes, not the prisma schema, not the repository. Do NOT touch MST (no MST-write surface in this spec).
- Do NOT touch shared state owned by another spec. `shared_state` is empty for this task; do not edit `prisma/schema.prisma`, the lockfile, next-config, or vitest-config beyond what this spec strictly requires (it requires none of them).
- Keep changes minimal: two new files under `src/lib/commerce/`. If a needed route does not exist beyond b7's three, REQUEST it as an additive b7 PR rather than adding a route here or splitting route ownership across tracks.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a failed fetch or a bad b7 response must produce a well-formed error the caller can see, not a silent null or a swallowed exception that looks like success.
- Secrets via Infisical only, never `.env`, never a literal in code or scripts.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section: `HttpCommerceDataSource` implements the seam and passes the in-memory double's contract suite; availability carries `availableQuantity` + `locationId` + `stale` + the advisory-only marker and the no-write-on-read test passes; any route needed beyond b7's three is requested as an additive b7 PR, not added here. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
