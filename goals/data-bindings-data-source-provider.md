---
task: framer-clone-datasource
wave: 1
spec: docs/specs/wave-1/data-bindings-data-source-provider-interface.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/data-bindings-data-source-provider-interface.md`. Define the abstract `DataSourceProvider` interface (Phase 1 read-only surface: `listCollections`, `getCollection`, `listRows`, `getRow`, `subscribe` polling), ship an `InMemoryDataSourceProvider` backed by hardcoded fixtures, expose `DataSourceProviderContext` + `useDataSource()` hook, and mount the in-memory provider near the root in `EditorApp` and `PreviewShell`. Reserve `WriteDataSourceProvider extends DataSourceProvider` for Phase 2 write methods (typed but not implemented).

## Read first

- `docs/specs/wave-1/data-bindings-data-source-provider-interface.md` (full spec)
- `src/components/EditorApp.tsx` and `src/components/preview/PreviewShell.tsx` (mount points for the provider)
- Any existing context/hook patterns in the repo to match style

## Definition of done (from spec)

- Code lands and typechecks (`pnpm build`)
- `pnpm test` passes including new `src/lib/bindings/dataSource/__tests__/inMemoryProvider.test.ts` (filter / sort / limit / subscribe coverage)
- Both `EditorApp.tsx` and `PreviewShell.tsx` wrap children with the in-memory provider for Phase 1
- Spec frontmatter status moved to `done` AND the row in `docs/specs/STATUS.md`
- Single commit on this branch with a clear message

## Open questions in the spec

Pick pragmatic defaults for THIS spec only and document the choice in the commit message. Do NOT escalate unless fundamentally blocked.

## Constraints

- Stay in the worktree at `~/software-dev/ERP-suite/projects/framer-clone-orch-datasource`. Do not modify files outside it.
- No HTTP client to `cms.lumitra.co` (separate track owns that).
- Phase 1 polling subscribe only; no WebSocket / SSE.
- Do not push to remote.
- When done and verified, output a final message that the task is complete.
