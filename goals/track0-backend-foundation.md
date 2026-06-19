---
task: track0-backend-foundation
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/track0-backend-foundation.md
depends_on: []
shared_state: [prisma, lockfile, next-config, vitest-config]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone backend foundation (Track 0, PILOT run)

This is a PILOT validating the orchestration loop. Build EXACTLY the Track 0 backend-foundation spec, nothing more, nothing from other tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/track0-backend-foundation.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Deps: `@prisma/client@^6.9.0` (runtime), `prisma@^6.9.0` (dev), `server-only` (runtime), `testcontainers` (dev).
- `prisma/schema.prisma`: SINGLE file, SINGLE Postgres schema (NOT multiSchema). Seed with the 8 `dt_*` models copied VERBATIM from `/Users/marlinjai/software-dev/ERP-suite/projects/data-table/packages/adapter-prisma/prisma/schema.prisma` (DtTable, DtColumn, SelectOption, DtRowSelectValue, DtRelation, DtFile, DtView, DtRow). `datasource db` uses `env("DATABASE_URL")`, `generator client = prisma-client-js`. Commit an initial migration.
- `src/server/db.ts`: `import 'server-only'` first line, a `globalThis`-cached `getPrismaClient()` HMR-safe singleton.
- `src/server/README.md`: server-only boundary contract + `src/app/api/*` route conventions + the `can()`-shaped admin-guard SEAM (do NOT implement auth, just the seam).
- `src/lib/api/respond.ts`: `jsonError` + `parseBody` matching the existing AI route envelope at `src/app/api/ai/edit/route.ts:94-110`.
- `src/app/api/health/db/route.ts`: `SELECT 1` liveness, `{ ok: true }` / 503 envelope, `runtime = 'nodejs'`.
- Test substrate: migrate `vitest.config.ts` to the `projects` form (jsdom for `src/**`, node for `src/server/**` + `src/lib/bindings/resolver/**`). Add a Dockerized-Postgres integration harness as a SEPARATE `pnpm test:integration` script kept OUT of the headless `pnpm test`.
- `package.json` scripts: `db:generate`, `db:migrate`, `db:deploy`, `test:integration`.

## Hard constraints (do NOT)

- Do NOT add commerce models (Track B owns those). Do NOT build the CMS adapter/repo (Track A `slice2-cms-server-adapter-and-repo`). Do NOT add the `@marlinjai/data-table-adapter-prisma` dep (slice2 owns that add). Do NOT implement auth (only the `can()`-shaped seam in the README). Do NOT touch MST. Keep `InMemoryDataSourceProvider` as the active client provider.
- Do NOT provision infrastructure (no Coolify, no real Postgres, no DNS). Document the `DATABASE_URL` contract only.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- `next build` MUST pass headless with a placeholder `DATABASE_URL` (the singleton is lazy). `pnpm test` MUST be unit-only (no Docker); integration tests live behind `pnpm test:integration`.
- Regression: the existing 16-test drag suite + the wave-1 bindings tests must stay green under the new `projects` vitest config.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical/Coolify only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
