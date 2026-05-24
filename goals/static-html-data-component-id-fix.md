---
task: framer-clone-static-html-fix
wave: 1
spec: docs/specs/wave-1/static-html-data-component-id-fix.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/static-html-data-component-id-fix.md` in the framer-clone repo. The spec describes a bug fix: the headless render path does not emit `data-component-id` and `data-inner-component-id` attributes. Move the attribute emission into the shared dispatch (`src/lib/renderer/createComponentElement.tsx`) so all renderers (editor, headless preview, static HTML) get them for free.

## Read first

- `docs/specs/wave-1/static-html-data-component-id-fix.md` (the full spec, including Files and changes table, API surface, test plan, and definition of done)
- `src/lib/renderer/createComponentElement.tsx` (current state)
- `src/lib/renderer/HeadlessComponentRenderer.tsx` (current state, including the comment that says headless does NOT attach data-* IDs)
- `src/components/ComponentRenderer.tsx` (the editor renderer; pay attention to where data-component-id / data-inner-component-id currently land in finalProps)

## Definition of done (from spec)

- Code lands and typechecks (`pnpm build`)
- `pnpm test` passes including a new `src/lib/renderer/__tests__/headlessDataAttributes.test.tsx`
- No regression in editor selection, drag resolution, or cross-viewport highlighting
- HeadlessComponentRenderer header comment updated (no longer says "no data-component-id attributes")
- Spec frontmatter status moved to `done` in `docs/specs/wave-1/static-html-data-component-id-fix.md` AND the row in `docs/specs/STATUS.md`
- Single commit on this branch with a clear message

## Open questions in the spec

The spec lists three architectural open questions ("Worker should propose, Marlin decides before merging"):

1. Identity attributes in `createComponentElement` (single source of truth) vs caller-supplied via finalProps?
2. FUNCTION component contract for spreading props to root: document, lint, or wrap?
3. `${breakpointId}-${componentId}` shape on static output: keep breakpoint-scoped or bare?

For these: pick the most pragmatic answer for THIS spec only (single source of truth for #1 because it minimizes diff and matches "no double-attribution" goal in scope; defer #2 and #3 with a clear note in the commit message). DO NOT escalate to the human; the spec authorizes you to propose. If you genuinely cannot decide on #1 because the codebase pulls you the other way, escalate.

## Constraints

- Stay in the worktree at `~/software-dev/ERP-suite/projects/framer-clone-orch`. Do not modify files outside it.
- No MST writes from the headless or static HTML paths (the spec is explicit on this).
- Do not push to remote.
- When done and verified, output a final message that the task is complete.
