---
task: trackc-commerce-binding-scope-frame-and-resolver
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-binding-scope-frame-and-resolver.md
depends_on: ["trackc-commerce-data-source-seam-and-dtos","slice2-read-binding-resolver-runtime"]
shared_state: ["binding-types"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce scope frames + resolver extension (Track C, storefront wave 2)

This is part of the framer-clone build (storefront track). Build EXACTLY the trackc-commerce-binding-scope-frame-and-resolver spec, nothing more, nothing from other specs or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-commerce-binding-scope-frame-and-resolver.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Extend the Track A React-free resolver with commerce scope frames so storefront components resolve `{{product.title}}`, `{{variant.sku}}`, `{{variant.price}}`, `{{availability.quantity}}` through the SAME mustache parser + scope chain + `applyBindings` machinery, against the typed commerce DTOs from `trackc-commerce-data-source-seam-and-dtos`.
- `src/lib/bindings/resolver/scope.ts` (edit): add `pushProductFrame(scope, product)`, `pushVariantFrame(scope, variant, price?)`, `pushAvailabilityFrame(scope, availability)`, parallel to the existing `pushRowFrame` / `pushCollectionFrame`.
- Teach `lookup` the roots `product.*`, `variant.*` (including `variant.price.*` resolved from the optional price folded into the variant frame), and `availability.*`. There is NO standalone `price.*` lookup root and NO `pushPriceFrame`; price is resolved as `variant.price.*` inside the variant frame.
- `src/lib/bindings/types.ts` (edit, `binding-types` shared state): extend the `BindableSlotMeta.scopeHint` union ADDITIVELY with exactly `'product' | 'variant' | 'availability'` (no `'price'`). Keep the existing `'row' | 'collection' | 'page' | 'any'` members intact.
- The `availability.*` frame is read-only advisory: resolving it carries the display-only / no-sell-permission comment. Resolution NEVER throws on a miss; `lookup` returns `undefined` against the innermost matching frame.
- `src/lib/bindings/resolver/__tests__/commerceScope.test.ts` (new, node project): assert product/variant/variant.price/availability resolution and the never-throw-on-miss behavior, under the Track A vitest node-env config.

## Hard constraints (do NOT)

- Do NOT build other specs' surface: no renderer wiring (the storefront renderers feed the frames, deferred), no editor binding picker (that is `slice2-editor-binding-picker`), no data source seam / DTOs (those come from `trackc-commerce-data-source-seam-and-dtos`, you only consume them), no CMS resolver work (Track A's `slice2-read-binding-resolver-runtime`, you only extend it).
- Do NOT add a standalone `price.*` root, a `pushPriceFrame`, or a `'price'` scopeHint. Price is `variant.price.*` only.
- Shared state: this spec EDITS `src/lib/bindings/types.ts` (the `binding-types` shared state, the `BindableSlotMeta.scopeHint` union consumed by the Track A picker). The edit MUST be additive and serial (after the CMS resolver lands). Do NOT touch any other shared state beyond `binding-types`. Do NOT touch MST (no `mst-tree`), no `prisma/schema.prisma`, no other spec's declared shared state. Keep changes minimal.
- The resolver MUST stay PURE, provider-free, and React-free (Node-evaluable for the publish path). ZERO React imports in `src/lib/bindings/resolver/**`; reuse the Track A grep/lint enforcement. The new test runs in the node-env vitest project, not jsdom.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a resolver miss returns `undefined` by contract (that is the designed behavior, not a swallow), but real failures (bad inputs, type errors, build/test/lint failures) must be visible, never silenced.
- Secrets via Infisical only, never a `.env` file, never a literal. No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.
- Regression: the existing drag suite + the wave-1 / Track A bindings tests must stay green under the vitest config.

## Definition of done

Every box in the spec's "Definition of done" section: the three frame-push functions land, `lookup` resolves the three roots (price via the variant frame), no React import in the resolver, and the `scopeHint` union is extended additively (the Track A picker tolerates the new values, enforced in `slice2-editor-binding-picker`). Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
