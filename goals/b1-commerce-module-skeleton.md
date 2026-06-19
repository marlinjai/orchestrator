---
task: b1-commerce-module-skeleton
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b1-commerce-module-skeleton.md
depends_on: ["track0-backend-foundation"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone commerce module skeleton (Commerce Engine, wave 1, b1)

This is part of the framer-clone build (June 2026 build, commerce-engine track). Build EXACTLY the b1-commerce-module-skeleton spec, nothing more, nothing from other specs or tracks. This spec stands up the `src/server/commerce/` bounded module that every later commerce spec (b2, b4, b5, b6) hangs off, with NO domain tables yet.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/commerce-engine/b1-commerce-module-skeleton.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/server/commerce/withTenant.ts`: `withTenant(prisma, schema, fn)` opens a `prisma.$transaction`, runs `SET LOCAL search_path TO ...` FIRST on the same connection (SET LOCAL scopes to the tx so a PgBouncer-pooled connection cannot leak one tenant's path into the next), then runs `fn` against the tx client. `schema` defaults to one exported `COMMERCE_SCHEMA` constant (single-tenant v1, constant schema).
- `src/server/commerce/repository/types.ts`: the transport-agnostic repo interfaces (`CatalogRepository`, `InventoryRepository`, `PricingRepository`, `OrderRepository`). Every method takes `tx: Prisma.TransactionClient` and never knows about HTTP or WebSocket.
- `prisma/sql/commerce-roles.sql`: SQL creating `commerce_app` (DML-only, the role the future `REVOKE UPDATE,DELETE ON stock_movement` applies to, used by the pooled app connection) and `commerce_ddl` (CREATE/ALTER, migration and provisioning, connects outside the tx pool). Include a docs note on why the REVOKE is only meaningful under two roles plus the PgBouncer `server_reset_query` requirement.
- `src/server/commerce/index.ts`: server barrel re-exporting the module surface.
- `src/server/commerce/__tests__/withTenant.test.ts`: node-project test asserting `SET LOCAL search_path` is issued inside the tx BEFORE `fn`, and that two sequential calls do not leak (constant-schema seam contract).
- `import 'server-only'` as the first line on all module code.
- The commerce auth guard is NOT re-created: commerce mutation routes REUSE the `slice2-admin-guard-stub` `requireAdmin` / `can()` seam (one constant workspace). Document this reuse; do not write a new guard.

## Hard constraints (do NOT)

- Do NOT add ANY domain model to `prisma/schema.prisma`. b2/b4/b5/b6 own those. `git diff prisma/schema.prisma` MUST be EMPTY in this spec. This spec declares `sharedState: []` and touches no shared state; it is pure scaffolding and adds ZERO models to the schema, so it must not run the prisma writer at all.
- Do NOT build the tenant registry, the outbox provisioning consumer, or the N-schema runner (deferred to E7). Do NOT implement real per-tenant search_path (E7; constant for v1).
- Do NOT import `@marlinjai/data-table-adapter-prisma`. data-table is NOT the system of record for stock or money (its `transaction()` is a verified no-op at `adapter.ts:894`); commerce uses purpose-built Prisma exclusively.
- Do NOT build any other spec's surface (no b2 catalog tables, no b4/b5/b6 inventory/pricing/order tables, no CMS-track files). Reuse the existing `track0-backend-foundation` PrismaClient singleton and the single `prisma/schema.prisma`; do not create a separate commerce backend foundation.
- Do NOT re-create the auth guard; reuse the `slice2-admin-guard-stub` seam and document the reuse. Do NOT implement auth itself.
- Keep changes minimal: only the files listed in the spec's "Files and changes" table.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed. A SET LOCAL failure or a tx failure must propagate, not be silently caught.
- Secrets via Infisical only, never `.env`, never a literal. The `DATABASE_URL` is supplied at verify time as a placeholder; do not commit real credentials and do not provision infrastructure.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
