---
task: trackc-order-create-checkout-stop
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-order-create-checkout-stop.md
depends_on: ["trackc-client-cart-state-and-cart-view","b6-minimal-orders","b3-guarded-reservation","slice2-admin-guard-stub"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone order-create checkout-stop (Storefront track, wave 2)

This is part of the framer-clone build-2026-06 (storefront track). Build EXACTLY the trackc-order-create-checkout-stop spec, nothing more, nothing from other specs or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/storefront/trackc-order-create-checkout-stop.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/app/api/commerce/orders/route.ts` (POST): the ONLY storefront-side write seam. Body is intentions only (`{ lines: { variantId: string; quantity: number }[] }`), with NO price or stock fields (assert that). Server is the sole author of money + stock.
- The route imports Track B's atomic `createOrder` (b6) and guarded `reserve` (b3) and runs them inside a REAL `prisma.$transaction` (NOT `adapter.transaction()`, which is the verified no-op). The server computes authoritative integer-cents totals and tax; the conditional decrement runs under b3's 3 stacked guards.
- Returns `201 { orderId, totalCents, currency }` on success, or `409 { ok: false, shortages: { variantId, needed, available }[] }` on a guarded-reserve rejection (typed per-line shortages).
- The mutation route is wrapped by the `slice2-admin-guard-stub` `can()`-shaped guard seam (one constant tenant) so the later auth-brain swap is an adapter change.
- `src/lib/renderer/commerce/CheckoutButton.tsx`: posts `useCart()` lines, STOPS at order-created. On success it clears the cart and shows an order confirmation. On a 409 shortage it does NOT silently clear the cart, surfaces which lines failed, and shows the next action (unhappy-path).
- Tests: `src/app/api/commerce/orders/__tests__/route.itest.ts` (integration: server-authoritative totals, oversell rejection, no client price/stock asserted) and `src/lib/renderer/commerce/__tests__/CheckoutButton.test.tsx` (success clears cart + confirmation; shortage keeps cart + shows failing lines).

## Hard constraints (do NOT)

- Do NOT build payment / Stripe / any pay-redirect; checkout STOPS at order-created (E8 deferred). Do NOT add a tax-engine call or invoice rendering (E8). The absence of payment/Stripe code is itself a documented DoD item.
- Do NOT re-implement `createOrder` or `reserve`; consume them from Track B (b6 owns `createOrder`, b3 owns the guarded `reserve`). Do NOT use `adapter.transaction()`; use a real `prisma.$transaction`.
- Do NOT touch shared state. This spec declares `sharedState: []` and `touchesSharedState: false`: do NOT append to `prisma/schema.prisma` (the commerce schema specs b2-b6 own serial appends to that single file and must not run concurrently with another prisma writer), do NOT touch the `mst-tree` shared state or add MST surface, do NOT change the lockfile/next-config/vitest-config owned by track0. Keep changes minimal and confined to the 4 files in the spec's Files-and-changes table.
- Do NOT build other specs' surface: not the client cart state/cart view (trackc-client-cart-state-and-cart-view owns `useCart()`), not the Track B atomic write internals, not the admin-guard stub itself (consume the seam, do not author it).
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a guarded-reserve rejection becomes a typed 409 the visitor sees, not a silent cart clear; a server fault surfaces, never a false success.
- Secrets via Infisical only, never `.env`, never a literal. `next build` MUST pass headless with a placeholder `DATABASE_URL`.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
