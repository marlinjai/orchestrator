---
task: slice2-read-only-data-components
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-read-only-data-components.md
depends_on: ["slice2-read-binding-resolver-runtime","slice2-prisma-datasource-provider"]
shared_state: []
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone read-only data components (slice2, CMS content tier)

This is part of the framer-clone build (CMS content tier, wave 2). Build EXACTLY the `slice2-read-only-data-components` spec, nothing more, nothing from other specs or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-read-only-data-components.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/renderer/data/CollectionRenderer.tsx` (new): reads the `collection` binding, calls `useDataSource().listRows(collectionId, query)`, pushes a row frame per row, and renders ONLY `children[0]` as the per-row template (the Events to gallery repeating component). It owns its children construction BEFORE the generic `children.map`.
- `src/lib/renderer/data/RecordViewRenderer.tsx` (new): resolves a SINGLE row from `{{page.params.id}}` and pushes one row frame. A non-existent id hits the empty/error path.
- `src/lib/renderer/createComponentElement.tsx` (edit): dispatch on `dataComponentKind` (the surviving `data-component-kind` attribute on the 3 registry entries `collection`/`recordView`/`tableView`) to the renderers, replacing the wave-1 dashed-box placeholder for BOUND nodes ONLY.
- `src/components/ComponentRenderer.tsx` + `src/lib/renderer/HeadlessComponentRenderer.tsx` (edit): both accept a `scope: BindingScope` prop, call `applyBindings` (the resolver's provider-free signature), and thread `scope` to children so descendants resolve `{{row.field}}`. Editor and headless MUST produce IDENTICAL output for the same bound tree.
- `src/components/ResponsivePageRenderer.tsx` (edit): construct the root `BindingScope` from page params.
- Structured filter/sort/limit live as a `Query` object on `props.query` (NOT a template expression). Each component subscribes via `dataSource.subscribe` for polling reactivity.
- `tableView` dispatch is RESERVED (the branch exists) but its renderer ships in `slice2-tableview-renderer`; until then a bound TableView falls back to the dashed-box placeholder with a `TableView pending` note. Tests: Collection + RecordView renderers under `src/lib/renderer/data/__tests__/`.

## Hard constraints (do NOT)

- Do NOT build `TableViewRenderer` (the `@marlinjai/data-table-react` wrap): that is the separate `slice2-tableview-renderer` leaf. Only RESERVE its dispatch branch with the pending-placeholder fallback.
- Do NOT change the lockfile or add the `data-table-react` dep: that add lives in the TableView spec, not here.
- Do NOT implement loading/empty/error directives as a shared helper: that is `slice2-data-loading-empty-error-states`. Thread a minimal inline state until that helper lands.
- Do NOT implement write bindings (read-only only). Do NOT reference doc-tier-core.
- Consume the resolver's PROVIDER-FREE `applyBindings`/`pushRowFrame` and `useDataSource()` as already shipped by the dependencies; do not redefine or fork them. This spec declares `sharedState: []` and touches no shared state: do not edit `prisma/schema.prisma`, the lockfile, the vitest config, or any state owned by another spec. Keep changes minimal and scoped to the files in the spec's table.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a bad/non-existent id, a failed `listRows`, or a missing binding must reach the empty/error path, never silently render as success.
- Secrets via Infisical only, never `.env`, never a literal.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine.

## Definition of done

Every box in the spec's "Definition of done" section: two renderers land, dispatch on `dataComponentKind`, first-child-as-template owned by the data renderers, scope threaded through both renderers, all renderer tests pass, editor/headless parity test green, dashed-box only when UNBOUND, STATUS row flipped. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
