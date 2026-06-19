---
task: slice2-editor-binding-picker
spec: /Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-editor-binding-picker.md
depends_on: ["slice2-read-only-data-components","slice2-content-type-management-ui"]
shared_state: ["mst-tree"]
verify: pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: framer-clone editor binding picker (slice2, CMS content tier, wave 3)

This is part of the framer-clone build (CMS content tier). Build EXACTLY the slice2-editor-binding-picker spec, nothing more, nothing from other slices or tracks.

## Authoritative spec (read it in full first; it IS the definition of done)

`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-editor-binding-picker.md`

That spec lives in the MAIN framer-clone checkout as an uncommitted planning doc, so read it at that absolute path. You work in THIS worktree (`--project`); write all code here.

## What to build (summary, the spec is authoritative)

- `BindingControl.tsx`: a per-slot bind/unbind control rendered next to each prop control declared in the registry's `bindableSlots` (`getBindableSlotsFor`). Unbound shows the static control plus a link icon; bound shows a read-only chip (`{{row.title}}`) plus unlink.
- `BindingPicker.tsx`: a popover with a scope tree (Page params, plus, when an ancestor is a Collection/RecordView, each column of the bound collection as `{{row.<column>}}`, columns resolved LIVE via `useDataSource().getCollection`), plus a free-form `{{...}}` input that red-borders on parse failure.
- `scopeIntrospection.ts`: `getAvailableScopeFrames(node)` walks ancestry to find the available row frame and returns the Collection ancestor's collectionId for deep nodes.
- `QueryBuilder.tsx`: a visual filter/sort/limit builder for Collection/TableView that writes `node.props.query` via the NEW `setQuery(query)` action.
- `DataSourceSection.tsx`: section wiring for the right sidebar.
- Committing a binding reuses the EXISTING `node.setBinding(slot, binding)` / `node.clearBinding(slot)` actions (already MST-WRITE). A broken binding (column deleted) shows a `column not found` warning chip with NO auto-migrate.
- The picker's `scopeHint` switch must default/`any`-branch on UNKNOWN hints so Track C's additive commerce `scopeHint` values (`product`, `variant`, `availability`) do not break it.
- Tests under `src/components/sidebars/right/__tests__/*.test.tsx` covering BindingPicker and QueryBuilder, matching the spec's full test plan.

## Hard constraints (do NOT)

- This spec TOUCHES the `mst-tree` shared state. It is the ONLY CMS-track spec that writes `mst-tree`. Keep new MST write surface MINIMAL: the single new action `setQuery(query: Query)` on `ComponentModel.ts` is the ONLY new MST action allowed, it writes into the EXISTING frozen props record, and it MUST be tagged with an `MST-WRITE` comment. Do NOT add new `.props()` FIELDS on the model. Reuse `setBinding` / `clearBinding` as-is.
- Tag EVERY picker-driven MST write with an `MST-WRITE` comment.
- Do NOT build other specs' surface: not the read-only data components (`slice2-read-only-data-components`), not the content-type management UI (`slice2-content-type-management-ui`), not write bindings / Form / LoginForm (epic E8/P6), not Hocuspocus/Yjs (epic E4). These are explicitly OUT of scope or deferred.
- Do NOT couple to doc-tier-core. Keep changes minimal and scoped to the right sidebar plus the one MST action plus the `scopeIntrospection` helper.
- Do NOT push to main, do NOT open a PR, do NOT merge. Commit to THIS worktree branch only. A human reviews and merges (Gate B).
- Errors must surface, never be swallowed: a parse failure red-borders the free-form input, a deleted column shows the `column not found` warning chip; do not silently drop these.
- Regression: no existing right-sidebar property tests may break, and the wider suite must stay green.
- No em-dashes or en-dashes in any file (use colons, parentheses, commas, periods). Hyphens in compound words are fine. Secrets via Infisical only, never `.env`, never a literal.

## Definition of done

Every box in the spec's "Definition of done" section (`/Users/marlinjai/software-dev/ERP-suite/projects/framer-clone/docs/specs/build-2026-06/cms-content-tier/slice2-editor-binding-picker.md`). Final gate (also the in-loop verify): `pnpm test && pnpm build && pnpm exec tsc --noEmit && pnpm lint` green, with the STATUS row in the spec flipped.
