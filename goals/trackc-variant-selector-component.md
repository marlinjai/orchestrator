---
task: trackc-variant-selector-component
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-variant-selector-component.md
depends_on: ["trackc-storefront-product-list-and-detail-renderers"]
shared_state: []
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone VariantSelector component (Track C storefront, wave 2)

This is part of the framer-clone build (build-2026-06, storefront track). Build EXACTLY the trackc-variant-selector-component spec, nothing more, nothing from other specs or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-variant-selector-component.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/renderer/commerce/VariantSelector.tsx` (new): renders one control per product option from the `options` DTO; selecting an option_value per option resolves the matching variant; re-pushes the SELECTED variant frame into the binding scope so descendant `{{variant.*}}` / `{{availability.*}}` re-resolve.
- `src/lib/commerce/selection.tsx` (new): `SelectedVariantContext`, `useSelectedVariant()`, and `resolveVariantFromSelection(product, variants, selection)`. This is the matrix walk: composite-coordinate match of the per-option selection against each `ProductVariantDTO.optionValues`. Client-only state (React state / a small context).
- Variant resolution via the variant <-> option_value matrix (the composite-coordinate match against `ProductVariantDTO.optionValues`), so picking a value per option resolves exactly one variant.
- Advisory availability text on the selected variant via `getAvailability(variantId)`: surface `In stock` / `Only N left` / `Out of stock` ADVISORILY, with the explicit comment that this reflects the advisory poll, NOT permission to sell (reserve-at-checkout is the real gate).
- Disable/grey-out of option combinations that resolve to no matching variant (unselectable combos).
- `useSelectedVariant()` exposed so the next spec (add-to-cart) can read the current selection.
- Tests in `src/lib/renderer/commerce/__tests__/VariantSelector.test.tsx` (new): selection -> variant -> re-resolve with a 2-option/4-variant fixture; unselectable combos; advisory text carries the no-sell-permission comment; an assertion that selecting NEVER triggers a write/reserve and NEVER touches MST.

## Hard constraints (do NOT)

- Selection state is CLIENT-SIDE only (React state / a small context). NEVER write it to MST and NEVER to the server: it is ephemeral UI state, not a stock or money fact. A test must assert no MST write and no server write on selection.
- This spec declares `sharedState: []` and `touchesSharedState: false`. Do NOT touch the `mst-tree` shared state or any shared state owned by another spec. Add no new MST surface.
- Do NOT build Cart (next spec) or checkout (later). Do NOT add any server write or any MST write. Do NOT build other specs' surface (e.g. the product list / detail renderers this depends on already exist upstream; consume them, do not re-implement them).
- Availability is advisory only: do NOT treat `getAvailability` as permission to sell; carry the comment that reserve-at-checkout is the gate. Errors from `getAvailability` must surface (visible to the user or the logs), never be swallowed into a silent "looks-available" state.
- Keep changes minimal: only the three files in the spec's "Files and changes" table.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: VariantSelector renders option controls, resolves the variant via the matrix, re-pushes the variant frame; unselectable combos handled; advisory availability + no-sell comment; no MST/server write; `useSelectedVariant()` available to the next spec. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
