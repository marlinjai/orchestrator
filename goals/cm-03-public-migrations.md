---
task: cm-03
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
depends_on: [cm-02]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **CM-03** (section "### CM-03 — Public migrations + registry bootstrap" of `docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md`, plus §4.4 "Public migrations"). Stand up the GLOBAL/public tier of the commerce → tenant-db model: run `migratePublic` so a fresh database gets the `ext` schema (pgcrypto, `gen_uuid_v7`, `touch_updated_at`) and the `public.tenant_groups` registry that every per-tenant `tg_<id>` schema is keyed on. This is the prerequisite the per-tenant DDL (CM-04) and provisioning (CM-11) build on.

## Read first (ground in the REAL tenant-db runner API)

- The plan's CM-03 section + §4.4. Commerce owns NO public commerce tables; the only public objects are `ext.*` and the `tenant_groups` / `tenant_migration_progress` registry that the runner itself owns.
- The installed package surface: `node_modules/@marlinjai/tenant-db/dist/index.d.ts`. The runner barrel exports `migratePublic`, `provisionTenant`, `migrateAllTenants`, `bootstrapAppRole`, `advisoryKeyFor`. The EXACT signature is `migratePublic(sql: Sql, migrations?: MigrationSet): Promise<string[]>` — it takes a postgres.js `Sql` and returns the applied migration ids. Default `PUBLIC_MIGRATIONS` is `001_ext_schema` + `002_tenant_groups`; pass NOTHING for the second arg (use the package default set, do NOT re-author the public migrations).
- The reference impl: `ERP-suite/projects/lumitra-infra/auth-brain/packages/tenant-db/src/runner.ts` (the `migratePublic` body + advisory-lock + `__tenant_db_migrations` bookkeeping) and `src/migrations/public/index.ts` (the real `001_ext_schema` / `002_tenant_groups` bodies: `CREATE SCHEMA IF NOT EXISTS ext`, `CREATE EXTENSION pgcrypto WITH SCHEMA ext`, `ext.gen_uuid_v7()`, `ext.touch_updated_at()`, `public.tenant_groups`, `public.tenant_migration_progress`). Do NOT copy these bodies into framer-clone — call the package's `migratePublic`, which owns them.
- framer-clone's `src/server/commerce/db.ts` (from CM-02): note the base singleton connects as the LOW-PRIVILEGE `commerce_app` role and is the wrong handle for DDL. `migratePublic` does DDL (CREATE SCHEMA/EXTENSION/TABLE), so it MUST run on a DIRECT owner connection from `COMMERCE_OWNER_DATABASE_URL` (`commerce_ddl`), `max: 1`, outside the pool — never the app base.
- An existing framer-clone `.itest.ts` for the Testcontainer convention (e.g. `src/server/commerce/__tests__/backstop.itest.ts` from CM-02, and `src/server/commerce/inventory/__tests__/schema.itest.ts` if present) — mirror `GenericContainer('postgres:16-alpine')`, trust auth, beforeAll/afterAll teardown.

## Definition of done

- New `src/server/commerce/provisioning/public.ts`: an async `migrateCommercePublic(connectionString?: string): Promise<string[]>` that opens a DIRECT postgres.js owner connection (default from `process.env.COMMERCE_OWNER_DATABASE_URL`, `max: 1`, `prepare: false`), calls `migratePublic(sql)` with the package-default migration set, closes the connection in a `finally`, and returns the applied ids. Read the owner URL at call time (not import) so `next build` needs no DB. Throw a clear error if `COMMERCE_OWNER_DATABASE_URL` is unset, naming that this is the OWNER role for DDL (distinct from the app role).
- A `pnpm db:public` script in `package.json` (a tsx entry, e.g. `scripts/db-public.ts`, or `tsx -e`) that invokes `migrateCommercePublic()` and logs the applied ids. Operator/deploy step, NOT runtime; it expects `COMMERCE_OWNER_DATABASE_URL` in the env (via the deploy's Infisical injection). Do NOT hardcode any connection string.
- Test (`.itest.ts`, Testcontainer `postgres:16-alpine`): run `migrateCommercePublic(<container owner url>)` against a fresh DB and assert via direct SQL probes: `ext` schema exists; `ext.gen_uuid_v7()` and `ext.touch_updated_at()` exist and are callable (`SELECT ext.gen_uuid_v7()` returns a uuid); `public.tenant_groups` and `public.tenant_migration_progress` tables exist. Then assert IDEMPOTENCE: a SECOND `migrateCommercePublic` call succeeds and applies nothing new (returns `[]` or the runner's already-applied signal — match whatever `migratePublic` actually returns on re-run; inspect the runner to get the exact contract, do not guess).
- `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass. Single conventional commit e.g. `feat(commerce): public migrations (ext + tenant_groups registry) via migratePublic (CM-03)`.

## Constraints

- Stay in this worktree. Files: new `src/server/commerce/provisioning/public.ts`, the `db:public` script (+ its tsx entry if separate), the `.itest.ts`, and the one `package.json` script line. Do NOT author the per-tenant migration set (CM-04 owns `001_inventory_ledger`..`006_enums`). Do NOT touch any repo/route, Prisma schema, `src/server/db.ts`, or `withTenant.ts`.
- `migratePublic` runs on the OWNER (`commerce_ddl`) connection ONLY — it does DDL. Never call it on the `commerce_app` base handle (ext-locked, no DDL privilege). Do not call `assertBackstop` on the owner connection (it would correctly throw; the owner legitimately has `public` on its path).
- Use the package's default `PUBLIC_MIGRATIONS`; do NOT re-implement `ext` / `tenant_groups` DDL in framer-clone. The package is the single source of truth for the public tier.
- Do not push to any remote. Output a final completion message.

## Notes

- This is the "commerce owns no public tables" tier from §4.4: the only global objects are `ext.*` (shared helpers) and the runner's own `tenant_groups` + migration-progress registry. The actual commerce tables (product, order, inventory, ...) are 100% per-tenant and land in CM-04 as `tg_<id>`-schema migrations.
- The `.itest.ts` suffix keeps the Docker test in `pnpm test:integration` (CI), out of the headless unit `pnpm test`. The in-loop verify is unit+build; if Docker is available locally, run `pnpm test:integration -t public` to self-verify, but the gate stays unit+build.
- Idempotence is a hard requirement: deploys re-run `db:public` safely. The runner already guards via `__tenant_db_migrations` bookkeeping + advisory lock; your test must PROVE the second run is a no-op, not assume it.
