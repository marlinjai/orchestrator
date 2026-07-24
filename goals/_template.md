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
- If the slice touches a MULTI-STEP STATEFUL FLOW (wizard, minting, checkout,
  review loop): tests MUST cover the revision paths, not just forward
  progression: (a) backtrack and change an earlier choice, asserting every
  piece of derived downstream state invalidates (and that keeping the same
  choice preserves it); (b) resume-from-persistence, asserting a persisted
  derived artifact whose source key no longer matches is discarded, not
  reattached; (c) clean re-entry after completion or failure. Rationale and
  the canonical prod bug this prevents:
  knowledge-base/standards/stateful-flow-testing.md (found live 2026-07-24:
  a re-rolled seed left a stale turnaround run attached because nothing
  keyed the run to its source).

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- Do not run destructive commands (the orchestrator's denylist will block most, but be deliberate).
- When done, output a final message that the task is complete.

## Notes

(Optional: anything Worker-specific. Examples: required env-var names the resulting code should reference, architectural invariants, "do NOT touch X area", deferred sub-tasks to add as `open_thread` entries.)
