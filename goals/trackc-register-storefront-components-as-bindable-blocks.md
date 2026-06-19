---
task: trackc-register-storefront-components-as-bindable-blocks
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-register-storefront-components-as-bindable-blocks.md
depends_on: ["trackc-storefront-product-list-and-detail-renderers","trackc-variant-selector-component","trackc-client-cart-state-and-cart-view","trackc-order-create-checkout-stop"]
shared_state: ["component-registry"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone storefront components as bindable canvas blocks (Track C, wave 2)

This is part of the framer-clone build (build-2026-06, storefront track). Build EXACTLY this spec, nothing more, nothing from other tracks or other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-register-storefront-components-as-bindable-blocks.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/componentRegistry.ts`: extend the CLOSED `ComponentCategory` union (currently `'basic' | 'layout' | 'data'` at line 31) with `'commerce'`, or tsc fails. This is the `component-registry` shared-state edit.
- `src/lib/componentRegistry.ts`: extend the `DataComponentKind` union with `'product-list' | 'product-detail' | 'variant-selector' | 'add-to-cart' | 'cart-view' | 'checkout-button'`.
- `src/lib/componentRegistry.ts`: add SIX entries (category `'commerce'`) mirroring the CMS `collection`/`recordView`/`tableView` entries, each with `bindableSlots` (ProductList: `products` slot; ProductDetail: `product` slot scopeHint `'product'`; descendants bind `{{product.*}}` / `{{variant.*}}` / `{{availability.*}}`), a `dataComponentKind`, and a `data-component-kind` HTML attribute marker. `getBindableSlotsFor` returns them.
- `src/lib/renderer/createComponentElement.tsx`: dispatch the six commerce kinds to the Track C renderers (the dependency specs); render the dashed-box placeholder ONLY when a commerce node is unbound.
- `src/components/sidebars/left/ComponentsPanel.tsx`: add a `listComponentsByCategory('commerce')` call plus a commerce section (the panel enumerates categories by hard-coded literals at lines 36-38, so the new category needs its own call and section to render).
- `src/components/EditorApp.tsx` and `src/components/preview/PreviewShell.tsx`: mount `CommerceDataSourceContext.Provider` (HTTP provider) alongside the existing `DataSourceProviderContext.Provider` at the symbol-anchor mount site (the `value={getSharedInMemoryDataSourceProvider()}` anchor, one site per file); keep the in-memory commerce double for tests.
- `src/lib/__tests__/componentRegistry.commerce.test.ts` (new): assert the six entries, their `bindableSlots`, `getBindableSlotsFor`, the extended `DataComponentKind`, and that a bound ProductList drag-drop renders the live fixture catalog.

## Hard constraints (do NOT)

- This spec touches the `component-registry` shared state and only that. Do NOT touch shared state owned by another spec. Do NOT touch the `mst-tree` (this is not an MST-write spec; no new MST surface). Do NOT touch `prisma/schema.prisma` (the commerce schema specs own that file serially; this spec is not a prisma writer).
- Do NOT build the Track C renderer/component surface itself (ProductList/Detail renderers, VariantSelector, CartView, CheckoutButton). Those are the four depends_on specs; consume them, do not reimplement them.
- Do NOT change the binding-picker beyond the new `scopeHint` values it already tolerates (the picker default-branches on unknown hints). Do NOT publish the components as `@marlinjai/*` packages (deferred until they stabilize; v1 keeps them in-repo).
- Keep changes minimal: edit only the files the spec names (`componentRegistry.ts`, `createComponentElement.tsx`, `ComponentsPanel.tsx`, `EditorApp.tsx`, `preview/PreviewShell.tsx`, plus the one new test).
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch ONLY. A human reviews and merges at Gate B.
- Errors must surface, never be swallowed: an unbound or misrouted commerce node must show the dashed-box placeholder or fail loudly, never silently render nothing that looks like success.
- Secrets via Infisical only, never a `.env` file, never a literal in code or config.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section (`ComponentCategory` extended with `'commerce'` and tsc green, the panel renders the commerce section, six entries plus dispatch plus provider mounts landed, a bound ProductList renders the fixture, STATUS row flipped). Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
