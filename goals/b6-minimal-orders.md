---
task: b6-minimal-orders
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b6-minimal-orders.md
depends_on: ["b5-pricing-and-tax"]
shared_state: ["prisma","migrations"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce engine, b6-minimal-orders

This is part of the framer-clone build (build-2026-06, commerce-engine track, wave 2). Build EXACTLY the b6-minimal-orders spec, nothing more, nothing from other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b6-minimal-orders.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `prisma/schema.prisma`: ADD the `Order` model (owns the order-level German tax fields tax_region, vat_id, customer_type, reverse_charge, net_or_gross, kleinunternehmer; plus server-computed integer-cents totals subtotal, tax_amount, total) and the `OrderLineItem` model (SNAPSHOT not reference: copies variant title/sku, resolved unit_price cents, quantity, tax_rate at creation; a loose `variant_ref` TEXT carrier + `variant_ref_source` select carrying none|datatable|owned, NEVER medusa).
- Finalize the b5 `CreditNote.credit_note_ref` FK so it points at `Order` (the corrected document is an Order/invoice; no DELETE path for the invoice).
- A new migration under `prisma/migrations/**` for the Order + OrderLineItem models + the CreditNote FK.
- `src/server/commerce/order/createOrder.ts`: cart payload to order in ONE `prisma.$transaction`: resolve prices via b5 `resolvePrice`, snapshot each line, compute server-side integer-cents subtotal/tax/total (never client-trusted), reserve each line via b3 `reserve()` with idempotency on the order's request_id; if any line short-stocks, the WHOLE transaction rolls back atomically and creates zero reservations.
- `src/server/commerce/repository/order.ts`: `OrderRepository`.
- `src/server/commerce/order/__tests__/createOrder.itest.ts` (integration): the 7 assertions from the spec test plan (price snapshot stability, server-computed cents totals ignoring client totals, atomic rollback on short-stock, variant_ref_source enum, B2B reverse_charge zero-VAT + legal-notice flag, kleinunternehmer Sec 19 VAT suppression, CreditNote-to-Order FK link).

## Consumer contracts (READ the spec's "Consumer contracts" section, honor exactly)

- b3 reserve: `createOrder` owns ONE `prisma.$transaction` and reserves every line INSIDE it by calling the INNER `reserve(tx, ...)` per line (so a short-stock rolls back ALL lines atomically), NOT `reserveWithRetry` (which owns its own separate tx). The inner `reserve` re-throws a `DuplicateRequestError` sentinel out of the tx on a `request_id` P2002; `createOrder` replicates b3's recovery at the ORDER level (roll back, then re-read + return the prior order in a FRESH transaction, keyed on the order's request_id). The naive in-transaction re-read fails (Postgres 25P02).
- b5 tax snapshot: `OrderLineItem` snapshots the FULL resolved tax treatment (applied tax_class, resolved rate, tax_amount integer cents, a `tax_treatment` discriminator standard|reduced|zero|reverse_charge|kleinunternehmer), NOT a bare tax_rate, so a reprint reproduces the legal invoice with zero recompute. Apply b5's non-negative money CHECK floor to order/line totals.

## Hard constraints (do NOT)

- This spec TOUCHES shared state. It appends to the SAME `prisma/schema.prisma` and `prisma/migrations/**` as the rest of the commerce schema chain (b2 through b6), and it is the LAST serial position (after b5). Do NOT run concurrently with another prisma writer; the orchestrator gates this via the `prisma` and `migrations` shared-state locks. Only add the b6 surface (Order, OrderLineItem, the CreditNote FK finalization), do not edit other specs' models.
- Do NOT build other specs' surface. The cart itself is client-side selection state (Track C); this spec owns ONLY the server-authoritative order WRITE. Consume b5 `resolvePrice` + the `CreditNote` entity and b3 `reserve()` as they exist; do not reimplement or modify them.
- Do NOT add Stripe, checkout, or any payment provider (deferred to E8). Do NOT add the bought tax-engine call, OSS accumulation, or invoice rendering (E8).
- The order write logic stays React-free and Node-evaluable (it runs under the node vitest project and inside `prisma.$transaction`). Do NOT touch MST or any client-side editor surface.
- Errors must surface, never be swallowed. A short-stock returns `{ ok: false, shortages }` and rolls the transaction back; do not silently succeed on a failed reservation. Totals are server-computed, never trust a client-sent total.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- `next build` MUST pass headless with a placeholder `DATABASE_URL` (the prisma singleton is lazy). The integration test (`*.itest.ts`) lives behind the integration harness and stays OUT of the headless `pnpm test`.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section (Order + OrderLineItem + finalized CreditNote FK land; `createOrder` resolves, snapshots, computes server cents totals, reserves via b3, rolls back atomically; all 7 integration assertions pass; `pnpm exec prisma generate` + migration apply succeed; STATUS row flipped). Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
