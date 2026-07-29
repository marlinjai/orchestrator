---
task: cm-09-recon
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
companion_of: cm-09
purpose: exact current semantics of order.ts + createOrder.ts the CM-09 Worker must reproduce in Kysely
---

# CM-09 recon: order repo + createOrder, exact semantics to reproduce

Sources: `src/server/commerce/repository/order.ts` and `src/server/commerce/order/createOrder.ts`.
Money/stock-critical. Depends on CM-07 (read repo merged) and CM-08 (reserve heart
merged): `createOrder` calls the INNER `reserve(trx, ...)` ported by CM-08, so build
on that exact signature. Read `cm-08-recon.md` for the reserve contract.

## order.ts (the thin data-access seam)

`nextOrderNumber(tx)` (order.ts:42) RAW: today
```
SELECT nextval('"commerce"."order_number_seq"') AS nextval
```
returns `bigint`, wrapped to `ORD-000001` via `formatOrderNumber(Number(nextval))`.
TARGET (per-tenant sequence, plan §5.2 site #3):
```
sql`SELECT nextval(${tenantSchemaRef(tgId)} || '.order_number_seq') AS nextval`
```
The sequence is now per-schema (CM-04 migration 005). Use `tenantSchemaRef` explicitly
(G3-safe); do NOT rely on a bare `order_number_seq` resolving under an injected path
(there is no SET LOCAL in app code). `nextval` returns `bigint`; keep `Number(...)`
(values are small) and the `ORD-` + 6-zero-pad format.

`insertOrder(tx, input)` -> `tx.order.create({...})` becomes
`trx.insertInto('order').values({...}).returningAll().executeTakeFirstOrThrow()`.
Map every column from CreateOrderRowInput: order_number, request_id, status (default
'confirmed'), currency_code, tax_region, vat_id, customer_type, reverse_charge,
net_or_gross, kleinunternehmer, tax_note, subtotal, tax_amount, total.

`insertLineItem(tx, input)` -> `trx.insertInto('order_line_item').values({...}).returningAll().executeTakeFirstOrThrow()`.
Columns: order_id, variant_title, variant_sku, unit_price, quantity, subtotal,
tax_class, tax_rate, tax_amount, tax_treatment, variant_ref, variant_ref_source.

`findByRequestId(tx, requestId)` -> `trx.selectFrom('order').selectAll().where('request_id','=',requestId).executeTakeFirst()`.

NOTE: `order` is a reserved word. With Kysely structured builders the identifier is
quoted automatically; in any raw fragment quote it (`"order"`).

## createOrder.ts (the ONE write transaction)

### The transaction (replace BOTH the isolation arg AND the hand-rolled SET LOCAL)

TODAY `runOrderTransaction`:
```
return prisma.$transaction(async (tx) => {
  await tx.$executeRawUnsafe(`SET LOCAL search_path TO "${COMMERCE_SCHEMA}"`);  // DELETE this line
  ... steps 1..6 ...
}, { isolationLevel: RESERVE_ISOLATION_LEVEL });
```
TARGET on the scoped `db = tenantDb(base, tgId)`:
```
return db.transaction().setIsolationLevel('read committed').execute(async (trx) => {
  ... steps 1..6 ...  // NO SET LOCAL: trx is already schema-qualified
});
```
The hand-rolled `SET LOCAL search_path` (createOrder.ts:289 AND the same line in
`resolvePriorOrder` at :435) is DELETED in both places (plan §5.2 site #2). G2 bans
runtime `SET search_path` in app code.

### Steps inside the transaction (order matters, preserve exactly)

1. Sequential idempotency: `findByRequestId(trx, cart.requestId)`; if a prior order
   exists, return `{ ok:true, orderId: prior.id }`.
2. For each cart line: `pricingRepository.resolvePrice(trx, variantId, {currency, priceListIds, quantity, now})`
   (CM-06 ported pricing). `null` -> throw (a missing price is an ERROR, not a
   shortage). `assertNonNegativeIntCents(unitPrice, ...)`.
3. Snapshot variant title/sku/tax_class: read the variant (with product.tax_class
   fallback) via a structured select; `taxClass = line.taxClass ?? variant.tax_class ?? variant.product.tax_class ?? null`.
   `base = unitPrice * quantity`; `computeLineTax(base, {...})`.
4. Server totals: accumulate `subtotal += lineTax.net; taxAmount += lineTax.tax; total += lineTax.gross`.
   `assertNonNegativeIntCents` on all three. cart.clientTotal is IGNORED entirely.
5. `nextOrderNumber(trx)` then `insertOrder(trx, {... server-computed totals ...})`.
6. For each line: `insertLineItem(trx, {...lines[i], orderId: order.id})`, then the
   INNER `reserve(trx, { inventoryItemId, locationId, needed: quantity, requestId: `${cart.requestId}:${i}`, refType:'order_line', refId: lineItem.id })`.
   If `!result.ok` -> `throw new OrderShortageError(result.shortages)` to abort and
   roll back the WHOLE order (every line + every prior reservation). MUST call the
   INNER `reserve` (NOT `reserveWithRetry`, which opens its own tx and would not roll
   back with the order).

### computeLineTax / resolveLineRate (pure functions, NO DB: keep verbatim)

- Integer-cents only (Math.round). kleinunternehmer beats reverse_charge beats rate.
- `resolveLineRate`: explicit rate overrides; `>MAX_RATE_BPS(10000)` throws; taxClass
  'reduced'->700, 'zero'->0, else STANDARD 1900.
- `treatmentForRate`: 0->'zero', 700->'reduced', else 'standard'.
- gross base: `tax = round(base*rate/(10000+rate))`; net base: `tax = round(base*rate/10000)`.
These are already DB-free; they do NOT change in the port.

### The duplicate / conflict recovery (preserve the order-level mirror)

`createOrder` outer catch:
- `OrderShortageError` -> return `{ ok:false, shortages }` (the tx already rolled back).
- `isReserveDuplicate(error)` (matches `error.name === 'DuplicateRequestError'`, the
  CM-08 inner-reserve sentinel) OR `isOrderRequestIdConflict(error)` -> a concurrent
  duplicate lost the UNIQUE race; re-read the winner in a FRESH transaction
  (`resolvePriorOrder`). Keep the name-tag match for `isReserveDuplicate` (the
  sentinel is not exported by reserve.ts).
- otherwise rethrow.

`isOrderRequestIdConflict` re-detection (was P2002 on order.request_id) TARGET:
`err.code === '23505' && err.constraint_name === 'order_request_id_key'` (or a
constraint_name containing `request_id`). Verify the postgres.js error field name in
`node_modules/postgres` types. Any other 23505 propagates unchanged.

`resolvePriorOrder(prisma, requestId)` opens a fresh `db.transaction().setIsolationLevel('read committed')`,
deletes its `SET LOCAL` line, re-reads `findByRequestId(trx, requestId)`, and returns
the prior order id; absent -> throw loudly (never a silent 500).

### validateCart (boundary, keep verbatim)

requestId/currency/taxRegion required; lines non-empty; reverseCharge requires
customerType 'b2b' AND a non-empty vatId; each line: inventoryItemId + variantId
required, quantity a positive int.

## The DB-enforced accounting identity (the test must rely on it)

Migration 005 has `CHECK (total = subtotal + tax_amount)`. createOrder computes
`total` as the sum of per-line gross and `subtotal`/`tax_amount` as the sums of net/tax.
For the identity to hold, `gross == net + tax` per line (it does, by construction in
computeLineTax). The isolation/createOrder test asserts a placed order's row satisfies
`total = subtotal + tax_amount`, and that the DB CHECK rejects a hand-built order row
that violates it.

## The test the goal requires (createOrder.isolation.spec.ts)

- Full placement: reserves + writes order + line items atomically; the order row is
  in `tg_a` only (a `tg_b` handle reading the order id returns ZERO).
- Shortage on ANY line rolls back the WHOLE order: zero orders, zero reservations.
- Concurrent duplicate order request_id: one order created, the loser re-reads the
  same orderId (no second order, no double reservation).
- `total = subtotal + tax_amount` holds on the persisted row.
