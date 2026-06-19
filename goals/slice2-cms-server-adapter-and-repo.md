---
task: slice2-cms-server-adapter-and-repo
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-cms-server-adapter-and-repo.md
depends_on: ["track0-backend-foundation"]
shared_state: ["lockfile"]
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone CMS server adapter + read repository (slice2, cms-content-tier)

This is part of the framer-clone build (build-2026-06, cms-content-tier track, wave 1). Build EXACTLY the slice2-cms-server-adapter-and-repo spec, nothing more, nothing from other slices or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-cms-server-adapter-and-repo.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Dependency add (this slice OWNS it): pin `"@marlinjai/data-table-adapter-prisma": "^0.2.2"` (direct from npm, real semver deps, no `workspace:*` leak; pulls `@marlinjai/data-table-adapter-shared@^0.2.2` + `@marlinjai/data-table-core@^0.3.0` transitively). Its `@prisma/client` must resolve to the single Track-0 6.x instance.
- `src/server/cms/adapterClient.ts`: `getCmsAdapter()` building a schema-bound `PrismaAdapter` from the Track-0 `getPrismaClient()`, bound to the constant single-tenant schema. First line `import 'server-only'`.
- `src/server/cms/columnTypeMap.ts`: `mapDataTableColumnType(dt)` mapping all THIRTEEN adapter-prisma input types to the 8 binding `ColumnType` outputs. LOSSY with explicit documented fallbacks (`multi_select` normalizes underscore to hyphen; `url`/`formula`/`rollup` fall back to text; `created_time`/`last_edited_time` fall back to date).
- `src/server/cms/repository.ts`: the READ repository (`listCollections`/`getCollection`/`listRows`/`getRow`) mapping adapter-prisma `Table` to `Collection`, `Column` to `Column` (via the type map), `Row` to `Row` (cells keyed by column id, multi-select arrays, file URLs as strings), `Query` passthrough/translation, `RowsPage` with cursor. Map onto the EXISTING binding shapes in `src/lib/bindings/dataSource/types.ts` (do NOT change those).
- `src/server/cms/withTenant.ts`: `withTenant(prisma, schema, fn)` with the `SET LOCAL search_path` SIGNATURE, body collapsed to the constant schema, tagged as the E7 multi-tenant seam (designed, not built).
- `src/server/cms/index.ts`: the server barrel (re-export `getCmsRepository` + types).
- Tests (node project): `__tests__/columnTypeMap.test.ts` covering all 13 inputs, `__tests__/repository.test.ts` covering `listRows` to `RowsPage` mapping (multi-select arrays + file URLs).
- A doc note recording that `adapter.transaction()` is a verified no-op (multi-row atomicity is the consumer's `prisma.$transaction` concern; single-entity DDL is atomic per the adapter).

## Hard constraints (do NOT)

- Do NOT build other slices' surface. WRITE methods (content-type create / field DDL) belong to `slice2-content-type-management-ui`; the client-facing React provider belongs to `slice2-prisma-datasource-provider`; the build-time hydrator belongs to `slice2-publish-read-binding-hydration`. This slice is READ-ONLY server tier under `src/server/cms/`.
- Do NOT add `@marlinjai/doc-tier-core` and do NOT add any lumitra-web dependency. There is NO shared package: framer-clone consumes adapter-prisma directly and keeps all repo-mapping code internal under `src/server/cms/`.
- This slice must stay React-free and Node-callable: NO React import anywhere under `src/server/cms/` (the hydrator must be able to call it). Enforce via grep/lint.
- Do NOT touch MST. No MST involvement of any kind.
- Do NOT introduce a second `@prisma/client`: reuse the Track-0 6.x singleton (`pnpm why @prisma/client` must still resolve to one instance).
- Shared state: this slice's ONLY declared shared state is `lockfile` (the dependency add). Do NOT touch `prisma/schema.prisma`, `next-config`, `vitest-config`, or any state owned by Track 0 or another slice beyond running the necessary install. Keep changes minimal and confined to `src/server/cms/**` plus the `package.json` dependency line.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a failed adapter call or mapping must throw or return a visible error, not a silent null that looks like success.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section (adapter-prisma@^0.2.2 installs cleanly, single Track-0 `@prisma/client`, all 13 column-type tests pass, repository read-mapping test passes for multi-select + file, `src/server/cms/**` is server-only and React-free, the no-op-transaction doc note recorded, no MST). Final gate (also the in-loop verify): `DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with the placeholder `DATABASE_URL` for the build step.
