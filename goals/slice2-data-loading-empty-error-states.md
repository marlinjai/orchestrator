---
task: slice2-data-loading-empty-error-states
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-data-loading-empty-error-states.md
depends_on: ["slice2-read-only-data-components"]
shared_state: []
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone loading / empty / error states for data-bound components (Slice 2, CMS content tier)

This is part of the framer-clone build (build-2026-06, cms-content-tier track, wave 2). Build EXACTLY the `slice2-data-loading-empty-error-states` spec, nothing more, nothing from other slices or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-data-loading-empty-error-states.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `src/lib/renderer/data/resolveDataState.ts`: a NEW pure helper `resolveDataState({ isLoading, rows, error, mode })` returning a directive `{ kind: 'loading' | 'empty' | 'error' | 'content'; message? }`. No React, no store access, no side effects: pure input to output.
- Directive semantics: LOADING maps to `props.loadingContent` or a minimal `Loading...`; EMPTY maps to `props.emptyContent` or `No items` / `Not found`; CONTENT renders the rows; ERROR splits on mode.
- Mode split: in `editor` mode, ERROR surfaces an inline error chip carrying the REAL error message (never swallow it); in `preview` mode (preview/headless/static emit), ERROR renders nothing for the slot, leaves no broken layout, and never throws during server-side rendering or static emit.
- Wire all three CMS renderers through the helper: `src/lib/renderer/data/CollectionRenderer.tsx`, `src/lib/renderer/data/RecordViewRenderer.tsx`, `src/lib/renderer/data/TableViewRenderer.tsx`. Route the loading/empty/error/content decision through `resolveDataState`; do not duplicate the branching inline.
- `src/lib/renderer/data/__tests__/resolveDataState.test.ts`: unit-test all four directives in BOTH modes, plus the editor error-chip-with-real-message case and the preview renders-nothing-and-never-throws case.
- Keep the happy-path renders unchanged: no regression to the CONTENT path of the three renderers.

## Hard constraints (do NOT)

- Do NOT build pagination (wave-3 `data-bindings-states-pagination-and-polish` owns it) and do NOT build write-binding states. CONTENT/loading/empty/error read-state only.
- Do NOT add or change the read-binding resolver, `useDataSource`, the datasource provider, or the registry. This slice CONSUMES the three renderers landed by `slice2-read-only-data-components`; it does not redefine them.
- Do NOT touch MST: this spec declares `touchesSharedState: false` and `sharedState: []`. Add no new MST surface and do not write to the `mst-tree` shared state owned by other specs. Do not touch `prisma/schema.prisma` (the commerce schema slices b2-b6 own serial appends there; stay out of that file entirely).
- `resolveDataState` MUST stay React-free and Node-evaluable (pure helper, no JSX, no hooks, no imports of React or the store). The JSX/chip rendering lives in the renderer `.tsx` files that call it, not in the helper.
- Keep changes minimal and confined to the five paths in the spec's "Files and changes" table (the new helper, its test, and the three renderer edits). Do not build any other spec's surface (no `slice2-read-only-data-components` renderer rewrites beyond routing through the helper, no Track C storefront renderers, no `TableViewRenderer` data-table-react dep changes).
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must SURFACE, never be swallowed: the editor error chip carries the real message; a swallowed error that looks like success is a bug. Preview/headless renders nothing for the errored slot but the error path is still exercised and tested.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section: `resolveDataState` pure plus unit-tested (four directives, both modes); editor error chip carries the real message and preview/headless renders nothing and never throws; all three renderers route through it; STATUS row flipped. Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green.
