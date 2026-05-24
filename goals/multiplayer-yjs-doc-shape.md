---
task: framer-clone-yjs-doc
wave: 1
spec: docs/specs/wave-1/multiplayer-yjs-doc-shape.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/multiplayer-yjs-doc-shape.md`. Define and freeze the Yjs document schema that mirrors the persisted fields of `ComponentModel` / `PageModel` / `ProjectModel`: factory `createEmptyProjectYDoc`, conversion helpers `mstSnapshotToYDoc` and `yDocToMstSnapshot`, schema version constant, and a Vitest fixture suite covering floating elements, viewport nodes, nested children, responsive style maps, and text-content props.

## Read first

- `docs/specs/wave-1/multiplayer-yjs-doc-shape.md` (full spec)
- `src/models/ComponentModel.ts`, `src/models/PageModel.ts`, `src/models/ProjectModel.ts` (the MST schemas being mirrored — read so the conversion helpers preserve every persisted field)
- Existing MST snapshot fixtures in tests, if any, to source realistic round-trip cases

## Definition of done (from spec)

- Code lands and typechecks (`pnpm build`)
- `pnpm test` passes including new `src/lib/multiplayer/yjsDocShape.test.ts`
- `yjs` added to dependencies (latest stable, MIT)
- New barrel `src/lib/multiplayer/index.ts` exports the public API
- Spec frontmatter status moved to `done` AND the row in `docs/specs/STATUS.md`
- Single commit on this branch with a clear message

## Open questions in the spec

Pick pragmatic defaults for THIS spec only and document the choice in the commit message. Do NOT escalate unless fundamentally blocked.

## Constraints

- Stay in the worktree at `~/software-dev/ERP-suite/projects/framer-clone-orch-yjs-doc`. Do not modify files outside it.
- No actual sync wiring — pure schema + conversion helpers + tests. Live wiring is a separate spec.
- No `Y.Text` for inline text in this pass (deferred per spec).
- Do not push to remote.
- When done and verified, output a final message that the task is complete.
