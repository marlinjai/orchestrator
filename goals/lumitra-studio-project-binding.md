---
task: lumitra-studio-project-binding
wave: 1
spec: docs/specs/wave-1/lumitra-studio-project-binding.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/lumitra-studio-project-binding.md` in the framer-clone repo.

## Read first

- The spec file (full contents: Goal, Scope, Files and changes, API surface, Test plan, Definition of done)
- Current `ProjectModel` definition and its persistence / snapshot pathway
- Any existing snapshot-migration helper to mirror its pattern

## Definition of done

Whatever the spec's "Definition of done" section lists. Plus, always:

- `pnpm test` passes
- `pnpm build` passes (typecheck + lint)
- Spec frontmatter `status: draft` becomes `status: done`
- The corresponding row in `docs/specs/STATUS.md` updated using the existing column format exactly. Do not add columns, do not reformat the table, do not add suffixes. Just change the Status cell from `draft` to `done`.
- Single commit on this branch with a conventional-commit message

## Constraints

- Stay in this worktree. Do not modify files outside it.
- No MST writes from headless or static HTML paths.
- No UI in this spec. Settings panel and snippet injection are Wave 2.
- Do not push to remote.
- When done, output a final message that the task is complete.
