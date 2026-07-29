---
task: cm-05
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
depends_on: [cm-04]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **CM-05** (section "### CM-05 — `CommerceDB` typed interface (kysely-codegen)" of `docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md`, plus §5 intro + §5.3). Produce the typed `CommerceDB` `Database` interface that every commerce repo (CM-06..CM-09) will be generic over, with the `public.`-prefix discipline that makes a missing global-table qualifier a COMPILE error. This unblocks the whole W2 repo-port wave.

## Read first

- The plan's CM-05 section, §3.4 (the `CommerceServerRepository` contract that CM-07 must keep), §5 intro (line ~121: "Global tables get the `public.` prefix key; commerce tables get bare keys"), and §5.3 (the GENERATED / trigger columns: `available_quantity` -> `Generated<number>`, `option_signature` -> `Generated<string>`, never inserted).
- The REAL discipline convention: `ERP-suite/projects/lumitra-infra/auth-brain/packages/tenant-db/src/database-shape.ts`. It exports `GlobalKey = \`public.${string}\`` and `TenantKey<K>` brand types and an `ExampleDatabase` showing the EXACT shape: global tables under a `public.<name>` key, per-tenant tables under a BARE key, so `tenantDb(base, tg).selectFrom('memberships')` compiles but `.selectFrom('users')` is a compile error (only `public.users` exists). Check the `@marlinjai/tenant-db` barrel (`node_modules/@marlinjai/tenant-db/dist/index.d.ts`) for whether `GlobalKey` / `TenantKey` are exported; if they are, import and use them, else mirror their definitions locally with a comment pointing at the package.
- The source of truth for the tables + columns: the CM-04 migration set `src/server/commerce/migrations/tenant/{000_enums..005_minimal_orders}.ts` (the 19 commerce tables, their columns, the GENERATED `available_quantity`, the trigger-maintained `option_signature`, the enum types). The generated interface MUST match this DDL exactly.
- framer-clone `src/server/commerce/db.ts` (CM-02): it currently exports an EMPTY placeholder `export interface CommerceDB {}` with a comment saying CM-05 replaces it. Replace that placeholder by re-exporting the real `CommerceDB` from `db-types.ts` (and keep `createNodeDb<CommerceDB>` wired to it). Do NOT change the base-singleton / backstop logic.
- kysely-codegen usage: it introspects a live Postgres schema. You will provision a `tg_<id>` schema in a Testcontainer (reuse the CM-04 pattern: `migratePublic` + `provisionTenant(... COMMERCE_TENANT_MIGRATIONS)`), point kysely-codegen at that schema, then post-process the output into the `public.`-discipline shape. Ground in kysely-codegen's actual CLI flags (`--url`, `--schema`, `--camel-case` if used); do not invent flags.

## Definition of done

- New `src/server/commerce/db-types.ts`: the `CommerceDB` interface following the database-shape discipline:
  - all 19 commerce tables under BARE keys (`product`, `product_option`, `product_option_value`, `product_variant`, `product_variant_option`, `price_set`, `price`, `price_rule`, `price_list`, `credit_note`, `credit_note_ref`, `inventory_item`, `stock_location`, `inventory_level`, `stock_movement`, `reservation`, `fulfillment_location_default`, `order`, `order_line_item`),
  - any global table the commerce layer reads (at minimum `public.tenant_groups`) under a `public.<name>` key,
  - column types matching the CM-04 DDL, with `available_quantity: Generated<number>` and `option_signature: Generated<string>` (import `Generated` from `kysely`) so Kysely never tries to INSERT/UPDATE them, and the enum columns typed as their string-union types.
- A codegen script (e.g. `scripts/commerce-codegen.ts` + a `pnpm db:codegen-commerce` script) that provisions a throwaway `tg_` schema in a container, runs kysely-codegen against it, and writes/refreshes `db-types.ts`. This documents how to regenerate when the DDL changes; the COMMITTED `db-types.ts` is what compiles (do not generate at build time). Add `kysely-codegen` as a devDependency.
- `src/server/commerce/db.ts` updated: the empty placeholder `CommerceDB` replaced by `export type { CommerceDB } from './db-types'` (or equivalent), `createNodeDb<CommerceDB>` still wired. No other change to db.ts.
- A type-discipline test `src/server/commerce/__tests__/type-discipline.test-d.ts` (or `.ts` checked by `tsc --noEmit`): use `@ts-expect-error` to PROVE that `tenantDb(getCommerceBase(), <tg>).selectFrom('tenant_groups')` (bare global) FAILS to compile while `.selectFrom('public.tenant_groups')` compiles, and that `.selectFrom('product')` (bare tenant table) compiles. The `@ts-expect-error` lines make `pnpm exec tsc --noEmit` (the verify gate) enforce the discipline in-loop, so it is gated without a separate typecheck runner. If vitest `*.test-d.ts` typecheck is already configured in the repo, use that; otherwise a plain `tsc`-checked file is fine.
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass. Single conventional commit e.g. `feat(commerce): CommerceDB typed interface + public-prefix discipline (CM-05)`.

## Constraints

- Stay in this worktree. Files: new `db-types.ts`, the codegen script + `package.json` script + devDep, the `db.ts` one-line `CommerceDB` rewire, the type-discipline test. Do NOT port any repo/route yet (CM-06..CM-10 own `catalog.ts`/`pricing.ts`/`read.ts`/`reserve.ts`/`order.ts`/`createOrder.ts`/routes). Do NOT touch the migrations, Prisma schema, or `withTenant.ts`.
- The generated types MUST reflect the CM-04 DDL, not a guess: `available_quantity` and `option_signature` are `Generated<>` (DB-maintained), the money columns are integers, the enum columns are their exact string unions. If kysely-codegen types something in a way that contradicts the DDL, fix the committed output and note it.
- Keep the `CommerceServerRepository` contract (hydrateBindings.ts:113-129) UNAFFECTED — CM-05 only adds types; CM-07 consumes them. Do not edit hydrateBindings.
- Testcontainer test stands up its own throwaway DB; use the container's TRUST auth (`POSTGRES_HOST_AUTH_METHOD: 'trust'` + username-only `postgresql://role@host` URIs, NO password literals) exactly like `backstop.itest.ts` / the CM-04 provision test — hardcoded passwords trip GitGuardian and block the PR.
- Do not push to any remote. Output a final completion message listing the table keys (which are `public.`-prefixed vs bare) and confirming the two `Generated<>` columns.

## Notes

- The whole point is "forgetting `public.` is a compile error" (database-shape.ts header). Globals live under `public.<name>` keys ONLY; per-tenant tables under bare keys ONLY; the two namespaces are disjoint. This is what stops a bare `selectFrom('tenant_groups')` inside a tenant query from silently resolving against (a decoy in) the tenant schema.
- kysely-codegen will likely emit schema-qualified or all-bare keys depending on flags; the post-process step is where you split globals to `public.` keys and strip the tenant-schema qualifier from commerce tables to bare keys. Commit the hand-reconciled result; the script is for regeneration, the file is the contract.
- `db-types.ts` is a pure type module (no runtime), so it does not need `server-only` and does not affect `next build` bundle size.
