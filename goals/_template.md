---
task: <task-id-kebab-case>
spec: <relative/path/to/spec.md inside the target repo, if applicable>
# Optional, for batch dispatch. See the autonomous-orchestration skill's
# "Batch dispatch (dependency-aware)" section.
# depends_on: [<other-task-id>, ...]   # must MERGE before this task launches
# shared_state: [<tag>, ...]           # canonical tags: lockfile, prisma, migrations, env, workspace, next-config, claude-md
---

# Goal

One-paragraph statement of what this task accomplishes. If a spec exists in the target repo, name it: "Implement the leaf spec at `<spec-path>`."

## Read first

- The spec file (full contents: Goal, Scope, Files and changes, API surface, Test plan, Definition of done)
- Any other files the spec lists as touchpoints
- Conventions/patterns relevant to the area (existing similar code, the target repo's CLAUDE.md or README)

## Definition of done

Whatever the spec's "Definition of done" section lists. Plus, always:

- `<test command>` passes (e.g. `pnpm test`, `pytest`, `go test ./...`)
- `<build command>` passes if the repo has one (typecheck + lint)
- Spec frontmatter `status: draft` becomes `status: done` (if there is a spec)
- Any shared-index row (STATUS.md, ROADMAP.md, etc.) updated using the existing column format exactly. Do not add columns, do not reformat the table, do not add suffixes.
- Single commit on this branch with a conventional-commit message describing the WHY

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- Do not run destructive commands (the orchestrator's denylist will block most, but be deliberate).
- When done, output a final message that the task is complete.

## Notes

(Optional: anything Worker-specific. Examples: required env-var names the resulting code should reference, architectural invariants, "do NOT touch X area", deferred sub-tasks to add as `open_thread` entries.)
