---
task: trackc-client-cart-state-and-cart-view
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-client-cart-state-and-cart-view.md
depends_on: ["trackc-variant-selector-component"]
shared_state: []
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone client cart state + CartView (Track C, storefront, wave 2)

This is part of the framer-clone build (build-2026-06, storefront track). Build EXACTLY the trackc-client-cart-state-and-cart-view spec, nothing more, nothing from other tracks or sibling specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-client-cart-state-and-cart-view.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- A CLIENT-SIDE cart only: cart contents are visitor selection state (a list of `{variantId, quantity}` lines). This is NOT a server-authoritative cart and NOT a money/stock fact; it is a shopping list of intentions. The authoritative reservation and totals happen later at order-create (next spec) inside Track B's atomic transaction.
- `src/lib/commerce/cart.tsx`: `CartContext`, `useCart()` (lines `{variantId, quantity}`; `add` / `setQuantity` / `remove` / `clear`; localStorage-backed, survives reload). `computeDisplaySubtotalCents(lines, prices)` returning integer cents, DISPLAY ONLY, with a hard comment that it is never authoritative.
- `src/lib/renderer/commerce/AddToCartButton.tsx`: reads `useSelectedVariant()`; adds the selected variant plus quantity; disabled when no variant is selected or advisory availability shows zero. The disable is a UX hint only, NOT the authority (comment it as such).
- `src/lib/renderer/commerce/CartView.tsx`: renders lines, each line resolves variant plus price Data Transfer Objects (DTOs) for DISPLAY, computes the DISPLAY-ONLY integer-cents subtotal labelled an estimate, supports quantity change and line removal, and shows an advisory-availability warning on a line whose availability dropped (the line is NOT auto-removed).
- All three surfaces route their per-line variant/price fetch through `resolveDataState`.
- Tests: `src/lib/commerce/__tests__/cart.test.ts` (persistence, display subtotal, assertion that no money is authored client-side) and `src/lib/renderer/commerce/__tests__/*.test.tsx` (AddToCart disable behaviour, CartView display). Assert that NO server write happens from any cart interaction.

## Hard constraints (do NOT)

- Do NOT build checkout / order-create (the next spec owns that). Do NOT touch payment (E8). Do NOT add any server cart, server route, or server write of any kind: every cart interaction stays client-side.
- Do NOT author money client-side. The display subtotal is the only computed money figure and it carries the not-authoritative comment; the authoritative total is computed server-side at order-create and is never trusted from the client (cross-check doc section 4.5: money is Layer-B authoritative).
- Do NOT build the variant selector itself (that is the upstream dependency `trackc-variant-selector-component`); only CONSUME its `useSelectedVariant()` hook.
- This spec declares `touchesSharedState: false` and `sharedState: []`. Do NOT touch the MST tree, the prisma schema, the lockfile beyond what the listed new files require, vitest config, or any other shared state owned by another spec. Keep changes minimal and scoped to the five files in the spec's Files-and-changes table.
- Do NOT build other specs' surface area. Stay inside `src/lib/commerce/` and `src/lib/renderer/commerce/` for the listed files only.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed (a silent failure that looks like success is worse than a loud one). Surface failures to the user or the logs.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: cart state persists to localStorage; AddToCart disable is a UX hint; CartView display subtotal is labelled an estimate with the not-authoritative comment; no money authored client-side; no server write from cart interactions; all three surfaces route through `resolveDataState`. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
