---
task: cm-02
spec: docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md
depends_on: [cm-01]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 2400
---

# Goal

Implement spec **CM-02** (section "### CM-02 — Roles + base connection + backstop" of `docs/plans/2026-06-27-commerce-tenant-db-migration-plan.md`, plus §3.3 + §4.1). Create the low-privilege commerce roles, the Node base Kysely singleton, and the startup `assertBackstop` guard. This is the connection + security foundation the whole commerce → tenant-db migration sits on.

## Read first (ground in the REAL tenant-db API)

- The plan's CM-02 section + §3.3 ("Base handle + per-request scoped handle") + §4.1 ("Roles + connection strings").
- The installed package: `node_modules/@marlinjai/tenant-db/dist/index.d.ts` and `dist/node.d.ts` (the `./node` subpath) — the EXACT API: `createNodeDb({ connectionString })` (or equivalent base factory), `assertBackstop`, `tenantDb`, `globalDb`, `tenantSchema`, `tenantSchemaRef`, `assertTenantGroupId`. Use the real signatures; do not invent.
- The reference impl + how auth-brain consumes it: `/Users/marlinjai/software-dev/ERP-suite/projects/lumitra-infra/auth-brain/packages/tenant-db/src/` (especially the connection/backstop modules) and any auth-brain consumer that builds the base + calls `assertBackstop`. The role SQL precedent: `auth-brain/packages/tenant-db/scripts/` or `src/` (the role/grant SQL the standard describes: a per-tenant low-privilege app role whose default `search_path = ext`).
- framer-clone's current `src/server/db.ts` (the lazy `getPrismaClient()` singleton) — the pattern to mirror for a lazy base singleton; do NOT remove Prisma (CMS/sites still use it; only commerce moves).

## Definition of done

- New `src/server/commerce/db.ts`: a lazy base singleton built with the tenant-db Node factory (`createNodeDb`/equivalent) from the **low-privilege `commerce_app`** role connection (`COMMERCE_APP_DATABASE_URL`), plus an exported `getCommerceBase()` and the per-request `tenantDb(base, tgId)` helper re-export. Mirror `db.ts`'s lazy-construct-on-first-call so `next build` needs no live DB. Call `assertBackstop(base)` at first use (or export an `assertCommerceBackstop()` the app calls at startup) — it must throw `BackstopError` if the connected role's default `search_path` includes `public` (i.e. someone pointed the app at the owner role), and pass when the role default is `ext`.
- The role SQL: a `prisma/sql/commerce-roles.sql` (or `src/server/commerce/sql/roles.sql`) creating `commerce_app` (low-privilege, default `search_path = ext`) and `commerce_ddl`/owner (provisioning), adapted from the tenant-db precedent. This is run by an operator/deploy step, not at runtime; the file is the source of truth.
- Infisical PLACEHOLDER scaffolding NOTE: the goal file's operator will scaffold `COMMERCE_APP_DATABASE_URL` + `COMMERCE_OWNER_DATABASE_URL` as `PLACEHOLDER_REPLACE_ME` in the framer Infisical project. Your code READS `process.env.COMMERCE_APP_DATABASE_URL` (app role) for the base, and the provisioning code (CM-11) reads `COMMERCE_OWNER_DATABASE_URL`. Do NOT hardcode connection strings; do NOT commit any real value.
- Test (Testcontainer `postgres:16-alpine`, `.itest.ts`): build a base against a role whose default path is `ext` → `assertBackstop` passes; build against the owner role (default path includes `public`) → `assertBackstop` throws `BackstopError`. Mirror the package's own `backstop.spec.ts` / `search-path-backstop.spec.ts`.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass. Single conventional commit e.g. `feat(commerce): tenant-db base singleton + commerce roles + assertBackstop (CM-02)`.

## Constraints

- Stay in this worktree. Files: new `src/server/commerce/db.ts`, the roles SQL, the backstop `.itest.ts`. Do NOT yet rewrite any repo/route (CM-06+); do NOT remove Prisma or the old `withTenant.ts` (CM-10/CM-13 own that). This spec ONLY stands up the connection + backstop.
- The base MUST use the low-privilege app role, never the owner role at runtime — `assertBackstop` enforces this and is the compliance backstop. Do not weaken it.
- Do not push to any remote. Output a final completion message.

## Notes

- The backstop is the crown of the "safe by construction" property: even if a misconfig points Kysely at a role whose path includes `public`, the app refuses to start rather than silently re-open the bare-name leak. Test BOTH directions.
- The `.itest.ts` suffix keeps the Docker test out of the headless `pnpm test` unit run and into `pnpm test:integration` (CI). The in-loop verify runs unit only; if Docker is available locally, run `pnpm test:integration -t backstop` to self-verify, but the gate stays unit+build.
