---
task: mt-08
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-08** (section "MT-08 - EditorApp hydrates a loaded snapshot"): rework the editor shell to APPLY a server-loaded project snapshot instead of fabricating `createProject('Framer Clone Demo')` on every mount. Pairs with MT-10 (which will pass the snapshot).

## Read first

- The MT-08 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/components/EditorApp.tsx` — currently `export default function EditorApp()` (NO props), `'use client'`. The init block (~lines 52-66, guarded by `initRef`) calls `rootStore.projectStore.createProject('Framer Clone Demo', ...)`, `editorUI.setCurrentProject(findProjectByTitle(...))`, `editorUI.setCurrentPage(currentProject?.findPageBySlug(''))`, then `getHistoryStore()?.clear()`. The clear is LOAD-BEARING: undoing past project creation destroys the page that `currentPage`/selection safeReferences point at.
- `src/stores/ProjectStore.ts` — `types.map(ProjectModel)`; `createProject` (heavy demo tree), `findProjectByTitle`, `getProject`. To ingest a snapshot you may add a SMALL MST action (e.g. `ingestProjectSnapshot(snapshot)` that does `self.projects.set(snapshot.id, snapshot)` and returns the id) — MST accepts a snapshot as a map value inside an action.
- `src/stores/EditorUIStore.ts` — `setCurrentProject(project?)`, `setCurrentPage(page?)` (auto-selects the page's appComponentTree). `currentProject`/`currentPage` are `safeReference`s.
- `src/models/ProjectModel.ts` — `ProjectSnapshotIn`/`ProjectSnapshotOut` (~lines 284-285). `findPageBySlug('')` returns the home page.
- `src/app/page.tsx` — the `ssr:false` dynamic mount `<EditorApp />` (no props). KEEP this as the no-snapshot dev mount.

## Definition of done

In `src/components/EditorApp.tsx`:
- Accept a prop: `export default function EditorApp({ projectSnapshot }: { projectSnapshot?: ProjectSnapshotOut })` (or `ProjectSnapshotIn` — pick the type that `ProjectStore` can ingest cleanly; a `SnapshotOut` is a valid `SnapshotIn` for ingestion).
- On first init (behind `initRef`):
  - If `projectSnapshot` is provided: ingest it into `rootStore.projectStore` (via a small `ingestProjectSnapshot` action if needed), `editorUI.setCurrentProject(<loaded project by id>)`, `editorUI.setCurrentPage(<its home page, findPageBySlug('') or first page>)`, then `getHistoryStore()?.clear()`. It must NO LONGER call `createProject('Framer Clone Demo')` in this branch.
  - If NO `projectSnapshot` (standalone dev mount, e.g. `/`): fall back to the CURRENT seed behavior (`createProject('Framer Clone Demo')` + set current + clear) so local `/` dev is UNCHANGED. Guard it, don't delete it.
- `src/app/page.tsx`: keep mounting `<EditorApp />` with no snapshot (dev seed path). No functional change required beyond confirming it still compiles with the new optional prop.

Test (jsdom project, or a store-level node test):
- Assert that hydrating snapshot A then snapshot B switches `currentProject` cleanly (currentProject id follows the latest ingested/selected snapshot; no stale safeReference). A store-level test of `ingestProjectSnapshot` + `setCurrentProject`/`setCurrentPage` is acceptable and cleaner than mounting the client component; or render `EditorApp` with a `projectSnapshot` prop and assert the store reflects it.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(editor): EditorApp hydrates a loaded project snapshot, falls back to seed (MT-08)`.

## Constraints

- Stay in this worktree. Files: `src/components/EditorApp.tsx`, `src/app/page.tsx`, and (if needed) a SMALL action in `src/stores/ProjectStore.ts`, plus a test. Do NOT restructure the stores broadly.
- Do NOT build the `/projects/[projectId]` route or pass a real snapshot from a server component — that is MT-10. This spec makes the shell ABLE to hydrate; the dev `/` mount still seeds.
- Preserve the `getHistoryStore()?.clear()` after init in BOTH branches (the safeReference invariant).
- Do not push to any remote. Output a final completion message.

## Notes

- The plan says the store is already multi-project-ready; a tiny `ingestProjectSnapshot` action is within spec (it's wiring, not a shape change). Keep it minimal.
- `EditorUIStore.selectComponent` has existing `console.log` debug noise — leave it; not in scope.
