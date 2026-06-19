---
task: b3-guarded-reservation
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b3-guarded-reservation.md
depends_on: ["b2-inventory-ledger-schema"]
shared_state: ["prisma","migrations"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce-engine b3-guarded-reservation (Wave 1)

This is part of the framer-clone build (build-2026-06, commerce-engine track). Build EXACTLY the b3-guarded-reservation spec, nothing more, nothing from other specs (b2, b4, b5, b6, b7).

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b3-guarded-reservation.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/server/commerce/inventory/reserve.ts` (new): the guarded conditional decrement `UPDATE inventory_level SET reserved_quantity = reserved_quantity + :needed, version = version + 1 WHERE inventory_item_id = :item AND location_id = :loc AND (stocked_quantity - reserved_quantity) >= :needed`, run inside a REAL `prisma.$transaction` (NEVER `adapter.transaction()`, the verified no-op).
- ISOLATION: the `$transaction` MUST run at Postgres DEFAULT READ COMMITTED. Do NOT open it at REPEATABLE READ or SERIALIZABLE (those raise a 40001 serialization failure instead of cleanly matching zero rows, turning the `{ok:false, shortages}` contract into a thrown error). The race test asserts READ COMMITTED.
- THREE STACKED GUARDS so oversell is structurally impossible: (1) the guarded UPDATE...WHERE available>=needed write-locks the row so concurrent reservers serialize and the loser matches zero rows -> `{ok:false, shortages}`; (2) the b2 `CHECK(reserved<=stocked)` backstop aborts any forgotten-guard path; (3) `UNIQUE(request_id)` on `stock_movement` makes the op idempotent against retries. Each reserve writes the append-only `stock_movement(reserve)` + the `reservation` row + the conditional level UPDATE in ONE `$transaction`.
- LOCATION SELECTION: `reserve` takes an explicit `locationId`; when omitted, a per-workspace default fulfillment location resolves it via `resolveLocation`. No reservation is ever created without a concrete location (`reservation.location_id` NOT NULL).
- KIT LOCK-ORDERING: a kit (one variant -> N items via `required_quantity`) locks its N item rows in ASCENDING `inventory_item_id` order inside the reservation transaction (removes the deadlock).
- TRANSFER-BALANCE: paired transfer movements share a `transfer_group_id`; a DEFERRED constraint trigger (ships as migration SQL) asserts the two halves sum to zero and both exist at commit, so a half-transfer cannot commit.
- `applyInventoryEffect` (new) handling reserve/release/fulfill/adjust via the same atomic pattern, with request_id idempotency.
- `prisma/migrations/**` (new): the deferred transfer-balance trigger + default-location config. `src/server/commerce/inventory/__tests__/reserve.itest.ts` (new integration): two-transaction race + the 6 guarantees + the isolation-level assertion.

## Hard constraints (do NOT)

- This spec is server-side commerce code: it must stay React-free and Node-evaluable. Do NOT add UI, components, or client code.
- Serial prisma chain: this spec APPENDS to the SAME `prisma/schema.prisma` and migration sequence as the other commerce specs (b2 through b6). It holds the `prisma`/`migrations` shared-state tags for its slot in the chain. Do NOT run concurrently with another prisma writer; the orchestrator serializes the chain via `depends_on: b2`.
- Do NOT build other specs' surface: NO orders (b6), NO pricing (b5), NO catalog (b4), NO REST (b7). Do NOT touch shared state owned by another spec beyond this spec's declared `prisma`/`migrations`. Do NOT touch MST. Keep changes minimal.
- Do NOT use `adapter.transaction()` anywhere (it is the verified no-op); always the real `prisma.$transaction`. NO `setStock`/`setPrice`/`merge` anywhere (read-only-author rule).
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a failed guard, a CHECK abort, a deferred-trigger rejection, or a missing location must propagate or return the explicit `{ok:false, shortages}` contract, never be silently dropped.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section (`reserve` runs the guarded UPDATE + reservation + stock_movement(reserve) in the caller's READ COMMITTED `$transaction`; `applyInventoryEffect` handles all four effects with request_id idempotency; the deferred transfer-balance trigger ships as a migration; all 6 race/guard guarantees + the isolation-level assertion pass; no setStock/setPrice/merge and no `adapter.transaction()`; STATUS row flipped). Final gate (also the in-loop verify): `DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
