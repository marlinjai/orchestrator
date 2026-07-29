---
task: cm-08-recon
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
companion_of: cm-08
purpose: exact current semantics of inventory/reserve.ts the CM-08 Worker must reproduce in Kysely
---

# CM-08 recon: the reserve heart, exact semantics to reproduce

Source: `src/server/commerce/inventory/reserve.ts`. This is money/stock-critical.
The Kysely port MUST preserve every behavior below. Do NOT redesign. Ground in
`node_modules/@marlinjai/tenant-db/dist/*.d.ts` for `tenantSchemaRef`, and read
`auth-brain/packages/tenant-db/src/raw.ts` for how a raw fragment names a tenant table.

## The transaction seam (today vs target)

TODAY:
```
export function reserveTransaction<T>(prisma, fn): Promise<T> {
  return prisma.$transaction(fn, { isolationLevel: Prisma.TransactionIsolationLevel.ReadCommitted });
}
```
The whole guarded-decrement proof relies on READ COMMITTED. REPEATABLE READ /
SERIALIZABLE raise 40001 instead of cleanly matching zero rows, breaking the
`{ ok:false, shortages }` contract. This is non-negotiable and test-pinned.

TARGET (Kysely on the already-schema-qualified scoped `db = tenantDb(base, tgId)`):
```
db.transaction().setIsolationLevel('read committed').execute(async (trx) => { ... })
```
`trx` is already schema-qualified (it inherits the `withSchema` from `db`), so the
hand-rolled `SET LOCAL search_path` that `createOrder` used is GONE (that lives in
CM-09; reserve.ts itself never set the path: it relied on Prisma `@@schema`
qualification + the route's `withTenant`). After the port, structured queries on
`trx` resolve to `tg_<id>`; raw fragments MUST use `tenantSchemaRef(tgId)`.

## The constant schema reference (today) -> tenantSchemaRef (target)

TODAY: `const SCHEMA = COMMERCE_SCHEMA; const LEVEL = '"commerce"."inventory_level"';`
The raw UPDATE/SELECT sites interpolate `${LEVEL}`. TARGET: replace `${LEVEL}` with
`${tenantSchemaRef(tgId)}.inventory_level` inside a Kysely `` sql`...` ``. The schema
is now per-tenant, so the constant string is removed and the scoped tgId is threaded
into reserve so the raw fragments can qualify. (The G3 guard bans a bare
`inventory_level` inside `sql``; tenantSchemaRef is the only legal way.) Plan §5.2
site #4..#8.

## The 3 stacked guards (preserve all three)

1. Guarded UPDATE `... WHERE (stocked_quantity - reserved_quantity) >= needed` takes
   a row write-lock; the loser re-evaluates against the winner's committed row and
   matches ZERO rows. Branch on the affected-row count.
2. DB CHECK `reserved_quantity <= stocked_quantity` (in migration 001) is the backstop.
3. UNIQUE(request_id) on stock_movement AND reservation makes every op idempotent.

## $executeRaw affected-row count -> Kysely numAffectedRows

TODAY `tx.$executeRawUnsafe(...)` returns the matched row count as a `number`; the
code branches `if (matched === 0)`. TARGET: a Kysely raw `sql``.execute(trx)` returns
`{ numAffectedRows: bigint }`. Branch on `result.numAffectedRows === 0n` (bigint
literal, NOT `=== 0`). This is the single most error-prone line: a `number`-vs-`bigint`
comparison silently never matches and would turn every reserve into a false success.

## The 4 raw UPDATE/SELECT bodies (verbatim WHERE clauses; bind every value)

guardedReserveUpdate (reserve.ts:358):
```
UPDATE <tenantSchemaRef>.inventory_level
   SET reserved_quantity = reserved_quantity + $needed,
       version = version + 1,
       updated_at = CURRENT_TIMESTAMP
 WHERE inventory_item_id = $itemId
   AND location_id = $locationId
   AND (stocked_quantity - reserved_quantity) >= $needed
```
matched===0 -> read available (stocked-reserved, floor 0) -> return { ok:false, shortages:[{inventoryItemId, locationId, needed, available}] }.

lockLevelsAscending (reserve.ts:468), the kit lock-order SELECT:
```
SELECT inventory_item_id, stocked_quantity, reserved_quantity
  FROM <tenantSchemaRef>.inventory_level
 WHERE location_id = $1
   AND inventory_item_id IN ($2, $3, ...)
 ORDER BY inventory_item_id ASC
 FOR UPDATE
```
`FOR UPDATE` + `ORDER BY inventory_item_id ASC` is the deadlock-free lock ordering.
Preserve it verbatim. The item ids are sorted ascending in JS before the query.

release UPDATE (reserve.ts:671): `SET reserved_quantity = reserved_quantity - $1 ... WHERE ... AND reserved_quantity >= $1`.
fulfill UPDATE (reserve.ts:704): `SET reserved_quantity = reserved_quantity - $1, stocked_quantity = stocked_quantity - $1 ... WHERE ... AND reserved_quantity >= $1 AND stocked_quantity >= $1`.
adjust UPDATE (reserve.ts:743): `SET stocked_quantity = stocked_quantity + $1 ... WHERE ... AND (stocked_quantity + $1) >= reserved_quantity`.
Each: matched===0 (numAffectedRows===0n) -> InventoryShortageError with the computed available.

## P2002 -> pg error-code 23505 re-detection (the second-most-critical port)

TODAY `isRequestIdUniqueViolation(error)` checks `error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2002'` then matches `meta.target` against `['stock_movement_request_id_key','reservation_request_id_key']` OR a target containing `request_id`.

TARGET: Prisma error classes are GONE. postgres.js raises an error with:
- `err.code === '23505'` (unique_violation), and
- `err.constraint_name` naming the violated index.
Re-detect: `err.code === '23505' && (err.constraint_name === 'stock_movement_request_id_key' || err.constraint_name === 'reservation_request_id_key')`. Confirm the postgres.js error field name against `node_modules/postgres` types (it is `constraint_name` on the PostgresError; verify, do not guess). Any OTHER 23505 (e.g. a real PK dup) MUST propagate unchanged, never swallowed.

## The DuplicateRequestError sentinel + fresh-tx re-read flow (preserve byte-for-byte)

- The inner `reserve(trx, args)` catches the 23505-on-request_id and throws the
  internal `DuplicateRequestError` (name-tagged) so it propagates OUT of the
  transaction. Postgres rolls the loser's tx back (undoing its OWN guarded
  decrement: NO double-decrement).
- The aborted transaction is in state 25P02, so the prior result CANNOT be re-read
  inside it. `reserveWithRetry` / `reserveKitWithRetry` / `applyInventoryEffectWithRetry`
  open a FRESH `reserveTransaction` and re-read the winner's committed reservation
  (`resolvePriorReservation` / `resolvePriorKitReservations`) or, for a plain effect,
  absorb the sentinel as a no-op.
- Keep `DuplicateRequestError` un-exported (it never escapes the module); keep its
  `.name` tag so `createOrder`'s `isReserveDuplicate` (CM-09) still matches by name.

## Idempotency pre-checks (sequential path)

`reserve`: pre-check `stockMovement.findUnique({ where: { requestId } })`; if present,
re-read the reservation by requestId and return it. Same for `reserveKit` (keyed on
the first component's `${kitRequestId}:${firstItemId}`) and `applyInventoryEffect`.
Port these structured reads to `trx.selectFrom('stock_movement').where('request_id','=',...).executeTakeFirst()` etc.

## Kit specifics

- `kitComponentRequestId(kitRequestId, itemId) = "${kitRequestId}:${itemId}"` (verbatim).
- Sort components ascending by inventoryItemId, lock all rows ascending FIRST
  (lockLevelsAscending), THEN check availability, THEN write. No partial reservation
  on a shortage.

## The concurrency test the goal requires (reserve.concurrency.spec.ts)

Two concurrent reservers of the same single-unit stock under READ COMMITTED: exactly
one gets `{ ok:true }`, the other gets `{ ok:false, shortages }` (NOT a thrown 40001).
A duplicate request_id across two concurrent reservers: the loser's tx rolls back
(no double-decrement), the WithRetry entrypoint re-reads and returns the SAME
reservation id. Kit lock acquired ascending (no deadlock for two overlapping kits).
