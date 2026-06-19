---
task: slice2-prisma-datasource-provider
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-prisma-datasource-provider.md
depends_on: ["slice2-cms-server-adapter-and-repo"]
shared_state: []
verify: DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone PrismaDataSourceProvider over /api/cms read routes (Slice 2, cms-content-tier wave 1)

This is part of the framer-clone build (build-2026-06, cms-content-tier track). Build EXACTLY this spec, nothing more, nothing from other specs.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-prisma-datasource-provider.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Four thin READ-only route handlers under `src/app/api/cms/`: `collections/route.ts` (GET list), `collections/[id]/route.ts` (GET one), `collections/[id]/rows/route.ts` (GET rows, Query in searchParams), `collections/[id]/rows/[rowId]/route.ts` (GET one row). All UNAUTHENTICATED for v1, `runtime = 'nodejs'`, delegating to `getCmsRepository()` (from the dependency spec's `src/server/cms` repo).
- `src/lib/bindings/dataSource/prismaProvider.ts`: `PrismaDataSourceProvider implements DataSourceProvider`, reaching the server over `fetch` to the `/api/cms/*` routes, with `subscribe()` implemented as polling (default 5s) that re-invokes `onChange`. Constructor takes `opts?: { baseUrl?: string; pollMs?: number }`.
- Swap the active provider at the two root mounts: replace `value={getSharedInMemoryDataSourceProvider()}` on `DataSourceProviderContext.Provider` in `src/components/EditorApp.tsx` and `src/components/preview/PreviewShell.tsx` with a `PrismaDataSourceProvider`. Anchor by SYMBOL, not line number; verify one site per file, unambiguous.
- Retain `InMemoryDataSourceProvider` as the isolated test double (do NOT delete); record a doc note that it is test-only now.
- Tests: `PrismaDataSourceProvider` passes the SAME contract suite `InMemoryDataSourceProvider` passes (listCollections / getCollection / listRows with filter+sort+limit / getRow / subscribe-fires-on-poll), with `fetch` mocked against the route shapes; route handlers tested with `getCmsRepository` mocked (mapped shapes, 404 on null, repo throw surfaces as a 5xx envelope never a swallowed empty 200). These node tests live under `src/app/api/cms/__tests__/*` and `src/lib/bindings/dataSource/__tests__/prismaProvider.test.ts`.
- Read routes return the success shapes (Collection[] / Collection / RowsPage / Row | null) and the Track-0 `{ error: { code, message } }` envelope on 4xx/5xx (use `src/lib/api/respond.ts`).

## Hard constraints (do NOT)

- Do NOT import `@marlinjai/doc-tier-core` (it is gone). Do NOT add ANY new `package.json` dependency: adapter-prisma + `@prisma/client` are added by Track 0 and the CMS server spec, not here.
- Do NOT build other specs' surface: no WRITE methods or write routes (those belong to the content-type-management-ui spec), no real-time push (polling only for Slice 2; SSE/socket is E6), no direct-RSC live-client reading (the build-time hydrator reads the repo directly; the live client goes over HTTP).
- Do NOT implement the CMS server adapter/repo (that is the dependency spec `slice2-cms-server-adapter-and-repo`, which owns `getCmsRepository()`); consume it, do not reimplement it.
- This spec touches NO shared state (`shared_state: []`, `touchesSharedState: false`). Do NOT touch shared state owned by another spec: no `prisma/schema.prisma` edit, no lockfile change (no dep add), no MST mutation, no vitest-config or next-config change. If something seems to need a shared-state edit, that is a signal you are out of scope; stop and keep the change minimal.
- This is a renderer-transparent swap: the renderer goes through `useDataSource()` and never imports a concrete provider, so NO renderer code changes. Keep the diff minimal.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must SURFACE, never be swallowed: a repo throw becomes a 5xx envelope, never an empty 200. Secrets via Infisical only, never `.env`, never a literal. No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods); hyphens in compound words are fine.
- `next build` MUST pass headless with a placeholder `DATABASE_URL` (no live Postgres); `pnpm test` MUST stay unit-only with `fetch` and `getCmsRepository` mocked. Existing renderer / drag / wave-1 bindings tests must stay green.

## Definition of done

Every box in the spec's "Definition of done" section. Final gate (also the in-loop verify): `DATABASE_URL='postgresql://placeholder:placeholder@localhost:5432/placeholder' pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with the placeholder `DATABASE_URL` for the build step.
