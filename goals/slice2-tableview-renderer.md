---
task: slice2-tableview-renderer
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-tableview-renderer.md
depends_on: ["slice2-read-only-data-components"]
shared_state: ["lockfile"]
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone TableView renderer (CMS content tier, slice2)

This is part of the framer-clone build (cms-content-tier track, wave 2). Build EXACTLY the slice2-tableview-renderer spec, nothing more, nothing from other slices or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-tableview-renderer.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- Add dep `@marlinjai/data-table-react@^0.3.1` (verified clean on the live npm registry; pulls `@marlinjai/data-table-core` and React 18/19 peer; NOT subject to the adapter-prisma `workspace:*` blocker). This touches the `lockfile` shared state.
- `src/lib/renderer/data/TableViewRenderer.tsx` (new): wraps the `@marlinjai/data-table-react` TableView in READ-ONLY mode, fed columns plus rows from the resolved collection via `useDataSource()`, with scope threaded through.
- Wire the `tableView` dispatch branch in `src/lib/renderer/createComponentElement.tsx` (the branch reserved by `slice2-read-only-data-components`) to route bound nodes to this renderer instead of the placeholder.
- Route through the `resolveDataState` helper if it has already landed; otherwise use a minimal inline state.
- `src/lib/renderer/data/__tests__/TableViewRenderer.test.tsx` (new): columns plus rows match the resolved collection, and `subscribe` re-renders on store mutation.
- API surface: `function TableViewRenderer(props: { node, scope }): ReactNode`.
- Fallback path: if read-only mode pulls editor-only deps into the published bundle, ship a hand-rolled read-only table instead and flag the situation to Marlin (do not silently accept the bloat).

## Hard constraints (do NOT)

- READ-ONLY only. Do NOT build write or edit-in-table (explicitly deferred by the spec).
- Do NOT build other slices' surface. The dispatch wiring and scope threading come FROM `slice2-read-only-data-components` (the dependency); consume them, do not re-implement them. Do NOT add the `@marlinjai/data-table-adapter-prisma` dep (a different slice owns that). The ONLY data-table dep here is `data-table-react`.
- Shared state: this slice declares `lockfile` only. Editing `package.json` plus the lockfile to add `data-table-react` is in-scope. Do NOT touch any other shared state (no `prisma/schema.prisma`, no MST tree, no `next-config`, no `vitest-config`) owned by another spec. Keep changes minimal and confined to the four files the spec lists.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed. A failed install, a fallback trigger, or a resolve miss must be visible (thrown, logged, or surfaced to the user and flagged to Marlin), never quietly hidden behind a happy-path render.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: `@marlinjai/data-table-react@^0.3.1` installs cleanly; TableViewRenderer renders the resolved collection read-only; `subscribe` re-renders; the fallback ships and is flagged if editor-only deps leak into the bundle; the `tableView` dispatch branch routes to this renderer for bound nodes. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
