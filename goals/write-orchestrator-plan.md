---
task: dogfood-write-plan
context: orchestrator-v1
---

# Goal

You are the autonomous orchestrator running its first dogfood task. Your job is
to read the design spec for the orchestrator and produce an executable
implementation plan for v2 (the next iteration after this v1 you are running on).

## Inputs

- Design spec: `~/software-dev/knowledge-base/docs/superpowers/specs/2026-05-08-autonomous-claude-orchestrator-design.md`
- Existing v1 plan: `~/software-dev/knowledge-base/docs/superpowers/plans/2026-05-08-autonomous-claude-orchestrator-plan.md`

## Output

Write an executable plan to:

  `~/software-dev/knowledge-base/docs/superpowers/plans/2026-05-09-autonomous-claude-orchestrator-v2-plan.md`

The plan must:

1. Conform to the document-lifecycle frontmatter schema (`type: plan`, `status:
   draft`, title, summary, tags, projects, date).
2. Cover the v2-deferred items from the v1 spec: compact-in-place handover,
   hard handover, `resume` CLI, loop detection, Haiku-API proxy override,
   macOS notification on escalate, multiple personas.
3. Use TDD task structure: each task has files (create/modify), test code,
   failing-run check, implementation, passing-run check, commit.
4. No placeholders ("TBD", "implement later", "similar to Task N"). Every step
   contains the actual code.
5. Reference real file paths from the orchestrator repo.

## Success criteria

- The plan file exists at the path above.
- The plan parses as Markdown with valid frontmatter.
- A human (Marlin) can hand the plan to a fresh agent and they can execute it
  without asking clarifying questions about scope.

## Constraints

- Stay in the knowledge-base repo for writes (the plan file). Read-only access
  to the orchestrator repo for reference.
- Do not modify the v1 spec or the v1 plan.
- Commit the plan file when done.
- When the plan is committed and verified, output a final message that the
  task is complete. The Decision Proxy will detect completion.
