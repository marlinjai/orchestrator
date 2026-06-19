---
task: slice2-content-type-management-ui
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-content-type-management-ui.md
depends_on: ["slice2-cms-server-adapter-and-repo","slice2-prisma-datasource-provider","slice2-admin-guard-stub"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone content-type management UI (slice2, CMS content tier)

This is part of the framer-clone build (build-2026-06, cms-content-tier track, wave 2). Build EXACTLY the slice2-content-type-management-ui spec, nothing more, nothing from other slices or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-content-type-management-ui.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- WRITE extension of `src/server/cms/repository.ts`: a `CmsWriteRepository extends CmsReadRepository` with `createCollection`/`renameCollection`/`deleteCollection`, `addColumn`/`renameColumn`/`retypeColumn`/`deleteColumn`, `createRow`/`updateRow`/`deleteRow`. These call the adapter-prisma DDL (`createTable`/`createColumn`/`createRow`/`updateRow`), NOT MST and NOT the no-op `adapter.transaction()`; single-entity DDL is atomic per adapter-prisma `atomicDDL/ddl.ts`.
- `/api/cms/*` WRITE routes: POST/PATCH/DELETE for collections, columns, and rows (the file table in the spec is exact). Each route is guarded by `requireAdmin(req)` from `slice2-admin-guard-stub`, sets `runtime = 'nodejs'`, and uses the Track-0 error envelope.
- Editor UI: a management panel reachable from the editor chrome (a "CMS"/"Content" panel), NOT a canvas component. `ContentManagerPanel.tsx` root plus `CollectionList.tsx` (collection CRUD), `FieldEditor.tsx` (column add/rename/retype/delete using the binding-layer `ColumnType` union), and `RowEditor.tsx` (basic row create/edit/delete).
- Errors surface LOUDLY: the route catches the SPECIFIC adapter-prisma collision/DDL error type (verified against `ddl.ts` and the adapter's error types), returns a typed envelope (for example a 409 `{ error: { code: 'collection_exists', ... } }`), and the UI renders it inline. If the adapter throws an opaque error, add a typed wrapper in `src/server/cms` and surface that.
- Empty state affordance: `Create your first collection`. The produced Events collection (fields title:text, date:date, cover:file, tags:multi-select) must appear in `listCollections`, the same store the binding picker reads.
- Tests: `src/server/cms/__tests__/repository.write.test.ts` (node project, write repo against a test schema) plus `src/components/cms/__tests__/*.test.tsx` for the panel UI and inline-error rendering. The specific-error-contract surfacing test must assert the typed error path, not a generic try/catch.

## Hard constraints (do NOT)

- Do NOT create `packages/doc-tier-core` and do NOT add or import `@marlinjai/doc-tier-core`. Do NOT touch any lumitra-web file. The write-repo extension lands in framer-clone `src/server/cms/repository.ts`.
- Do NOT write MST. This spec writes no MST; the management panel does NOT touch the `mst-tree` shared state. KEEP the adapter-prisma `createTable`/`createColumn` DDL and the specific-error-contract surfacing.
- Do NOT build other specs' surface: not the read repo + adapterClient (`slice2-cms-server-adapter-and-repo` owns that), not the datasource-provider route conventions (`slice2-prisma-datasource-provider`), not the admin guard itself (`slice2-admin-guard-stub` owns `requireAdmin`). Consume those, do not reimplement them.
- Do NOT touch shared state owned by another spec. This spec declares an EMPTY `shared_state` ([]); keep all changes confined to `src/server/cms/**`, `src/app/api/cms/**`, and `src/components/cms/**`. Do not edit `prisma/schema.prisma`, the lockfile, the next config, or the vitest config beyond what is strictly required to register the new node/jsdom test files (and only if not already covered by Track 0's `projects` config).
- Out of scope (explicitly deferred): multi-row atomic writes, MST writes, and real `withTenant` multi-tenancy (E7). Use the constant-schema seam; do not build multi-tenancy here.
- Read routes must still work unauthenticated; only the WRITE routes are admin-guarded. Reject writes with 401/403 when `requireAdmin` fails.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a silent failure that looks like success is a bug. The route must surface the typed adapter error and the UI must render it inline.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section (full collection/field/row CRUD from the UI; Events in `listCollections`; write repo + write routes in `src/server/cms` + `src/app/api/cms` with NO `packages/doc-tier-core` and NO lumitra-web file; specific-error-contract surfacing test passing; write routes guarded by `requireAdmin`; empty-state affordance; panel does NOT write MST). Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with a placeholder `DATABASE_URL` for the build step.
