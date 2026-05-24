---
task: ai-pattern-a-mst-snapshot-serializer
wave: 1
spec: docs/specs/wave-1/ai-pattern-a-mst-snapshot-serializer.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/ai-pattern-a-mst-snapshot-serializer.md` in the framer-clone repo.

## Read first

- The spec file (full contents: Goal, Scope, Files and changes, API surface, Test plan, Definition of done)
- The current MST models (`ProjectModel`, `PageModel`, `ComponentModel`, `componentRegistry.ts`, breakpoints) so the serializer mirrors the actual shape
- Any existing snapshot or serialization helpers to avoid duplication

## Definition of done

Whatever the spec's "Definition of done" section lists. Plus, always:

- `pnpm test` passes
- `pnpm build` passes (typecheck + lint)
- Spec frontmatter `status: draft` becomes `status: done`
- The corresponding row in `docs/specs/STATUS.md` updated using the existing column format exactly. Do not add columns, do not reformat the table, do not add suffixes. Just change the Status cell from `draft` to `done`.
- Single commit on this branch with a conventional-commit message

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Serializer is READ-ONLY. No MST writes. No mutations.
- Determinism is load-bearing for prompt caching: stable key ordering, no Date.now, no random, strip MST-internal fields.
- Do not push to remote.
- When done, output a final message that the task is complete.
