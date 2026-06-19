---
task: trackc-storefront-product-list-and-detail-renderers
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-storefront-product-list-and-detail-renderers.md
depends_on: ["trackc-commerce-binding-scope-frame-and-resolver","trackc-commerce-http-provider-and-read-routes","slice2-read-only-data-components","slice2-data-loading-empty-error-states"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone storefront ProductList + ProductDetail renderers (Track C, storefront wave 2)

This is part of the framer-clone build (build-2026-06, storefront track). Build EXACTLY this spec, nothing more, nothing from other tracks or other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-storefront-product-list-and-detail-renderers.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/renderer/commerce/ProductListRenderer.tsx` (new): reads its `products` binding plus an optional `CommerceQuery` on `props.query`, calls `listProducts` via `useCommerceDataSource()`, pushes a product scope frame per product, and repeats `children[0]` as the per-product card template (first-child-as-template, the storefront analog of the CMS Events to gallery pattern). Each descendant `{{product.field}}` resolves to that iteration's product.
- `src/lib/renderer/commerce/ProductDetailRenderer.tsx` (new): resolves a single product from `{{page.params.handle}}`, pushes a product frame exposing `{{product.*}}`, and resolves the default/first variant into a variant frame so `{{variant.price}}` plus `{{availability.quantity}}` render to descendants.
- Both renderers route through the shared `resolveDataState` for all four directives (loading, empty, error, content) in BOTH modes: editor inline chip, preview/headless renders nothing. Cover zero products, product-not-found, and fetch error; never throw during SSR or static emit.
- Model both renderers EXACTLY on the CMS `CollectionRenderer` / `RecordViewRenderer` (first-child-as-template repeat, scope frame per iteration, scope threaded through children), but resolve the typed commerce graph via `useCommerceDataSource()`.
- Read-only only: never write stock, money, or any commerce mutation.
- `subscribe` must re-render on store change.
- Tests in `src/lib/renderer/commerce/__tests__/*.test.tsx` (new): per renderer plus editor/headless parity, matching the spec's Test plan and Definition of done.

## Hard constraints (do NOT)

- This spec is React-bound canvas renderers; React in the renderer files is correct. Do NOT touch the commerce resolver layer (that is `trackc-commerce-binding-scope-frame-and-resolver`, which must stay React-free / Node-evaluable); consume it, do not edit it.
- Do NOT build the variant selector (next spec). Do NOT build cart or checkout (later specs).
- Do NOT do the registry/dispatch wiring. `createComponentElement`'s `dataComponentKind` branch is extended to the commerce kinds in the SEPARATE register spec; until then dispatch is reserved. Do NOT add or alter that registration here.
- Do NOT add commerce HTTP provider or read routes (`trackc-commerce-http-provider-and-read-routes` owns those); consume them.
- Do NOT touch MST. The spec declares `touchesSharedState: false` and `sharedState: []`, so do NOT touch the `mst-tree` shared state, the `prisma/schema.prisma` file, the lockfile, the next config, or the vitest config beyond what these new files strictly require. Keep changes minimal and scoped to the two new renderer files plus their tests.
- Do NOT provision infrastructure (no Coolify, no real Postgres, no DNS).
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed; a silent failure that looks like success is worse than a loud one. The not-found and fetch-error paths must reach `resolveDataState` (editor chip / headless renders nothing), never a swallowed exception.
- Regression: existing renderer + bindings tests must stay green.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: both renderers land with first-child-as-template and product (plus default variant) frames pushed; both route through `resolveDataState` across all four directives in both modes; `subscribe` re-renders; the editor/headless parity test is green. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
