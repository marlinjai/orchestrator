---
task: data-bindings-component-registry-bindable-slots
wave: 1
spec: docs/specs/wave-1/data-bindings-component-registry-bindable-slots.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/data-bindings-component-registry-bindable-slots.md` in the framer-clone repo.

## Read first

- The spec file (full contents: Goal, Scope, Files and changes, API surface, Test plan, Definition of done)
- The dependency spec `docs/specs/wave-1/data-bindings-binding-shape-on-component-model.md` (status: done) so this spec layers on top correctly
- Current `componentRegistry.ts` and the `ComponentRegistryEntry` type
- ComponentsPanel to confirm the `category: 'data'` extension renders correctly

## Definition of done

Whatever the spec's "Definition of done" section lists. Plus, always:

- `pnpm test` passes
- `pnpm build` passes (typecheck + lint)
- Spec frontmatter `status: draft` becomes `status: done`
- The corresponding row in `docs/specs/STATUS.md` updated using the existing column format exactly. Do not add columns, do not reformat the table, do not add suffixes. Just change the Status cell from `draft` to `done`.
- Single commit on this branch with a conventional-commit message

## Constraints

- Stay in this worktree. Do not modify files outside it.
- This is the REGISTRY-SHAPE seam, not the renderer. Actual data-component rendering is Wave 2.
- No MST writes from headless or static HTML paths.
- Do not push to remote.
- When done, output a final message that the task is complete.
