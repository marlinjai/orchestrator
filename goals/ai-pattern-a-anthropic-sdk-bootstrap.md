---
task: ai-pattern-a-anthropic-sdk-bootstrap
wave: 1
spec: docs/specs/wave-1/ai-pattern-a-anthropic-sdk-bootstrap.md
---

# Goal

Implement the leaf spec at `docs/specs/wave-1/ai-pattern-a-anthropic-sdk-bootstrap.md` in the framer-clone repo.

## Read first

- The spec file (full contents: Goal, Scope, Files and changes, API surface, Test plan, Definition of done)
- `package.json` to confirm where to add the `@anthropic-ai/sdk` dependency
- Any existing `src/app/api/` route to mirror conventions
- Any existing logger / env-loading utilities the codebase already provides

## Definition of done

Whatever the spec's "Definition of done" section lists. Plus, always:

- `pnpm test` passes
- `pnpm build` passes (typecheck + lint)
- Spec frontmatter `status: draft` becomes `status: done`
- The corresponding row in `docs/specs/STATUS.md` updated using the existing column format exactly. Do not add columns, do not reformat the table, do not add suffixes. Just change the Status cell from `draft` to `done`.
- Single commit on this branch with a conventional-commit message

## Secrets

`ANTHROPIC_API_KEY` is provided through the orchestrator's environment via Infisical at launch time. Read it from `process.env.ANTHROPIC_API_KEY` in the Anthropic client singleton. Do NOT hardcode keys, do NOT commit any `.env` file, and do NOT print the key to logs.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- No MST writes from headless or static HTML paths.
- Do not push to remote.
- When done, output a final message that the task is complete.
