---
task: framer-content-agent
spec: docs/specs/build-2026-06/cms-content-tier/slice4-content-agent-phase2.md
shared_state: [prisma, migrations]
verify: DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Implement the LOCKED leaf spec at `docs/specs/build-2026-06/cms-content-tier/slice4-content-agent-phase2.md`
in full: the right-rail natural-language **Content agent** column in `CmsWorkspaceOverlay`. The agent
takes NL instructions ("Generate 5 blog posts", "Import events.csv", "Translate all titles to German"),
executes them as Anthropic tool-use tool calls against the existing admin-guarded CMS data layer,
streams reasoning + a change summary over Server-Sent Events (SSE), and records every mutation with an
inverse so the user can **Undo all** in one click.

The spec is LOCKED: all five Lead-required fixes are already folded in (translate_field Option A,
admin-auth-in-async-context fix, fetch-based SSE client, archive-based removal, `vi.mock` for the
Anthropic client). Do NOT re-litigate any resolved decision in section 2. Build exactly the spec.

## Read first (full contents)

- The spec file above end to end: sections 1 (scope), 3 (15-tool schema list + Zod input schemas),
  4 (route + streaming contract, including 4A admin-auth-in-async-context), 5 (AgentRun/AgentChange
  persistence + Undo route), 6 (prompt cache), 7 (UI component breakdown), 8 (model bump), 9 (headless
  test plan), 11 (files-and-changes table), 12 (definition of done).
- The pattern this MIRRORS: `src/app/api/ai/edit/route.ts` (existing Anthropic tool-use loop + SSE) and
  `src/lib/ai/anthropicClient.ts` (`AI_MODELS`, `buildSystemPrompt`, prompt-cache breakpoint).
- The data layer the executor calls DIRECTLY: `src/server/cms/` (the `getCmsAdapter()` / `CmsAdapter`
  surface, the `PrismaAdapter` archive/getRows behavior referenced in section 2) and
  `src/server/cms/actions.ts` (admin-guarded surface, for the auth contract only — the executor calls
  the adapter directly, NOT actions).
- The container being extended: `src/components/cms/grid/CmsWorkspaceOverlay.tsx` (the phase-1
  `[rail | grid]` layout with the RESERVED right slot) and existing `src/components/ui/*` primitives.
- The admin-auth helper area: `src/server/auth/adminAction.ts` (add `verifyAdminCookie(req: Request)`
  that reads `request.cookies`, NOT `next/headers`).

## Definition of done

Everything in spec section 12 (all 14 checkboxes), plus the always-on gates:

- `DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` all green.
- The Prisma migration for `AgentRun` + `AgentChange` + `AgentRunStatus` (both in `@@schema("public")`)
  is a real migration file under `prisma/migrations/<timestamp>_add_agent_run_change/migration.sql`,
  with valid `CREATE TABLE` / `CREATE TYPE` SQL matching the schema.prisma additions. Do NOT rely on
  `prisma migrate dev` connecting to a DB during verify; hand-author or `prisma migrate diff` the SQL so
  it is committed and the migration history is consistent.
- The OPUS model bump in `src/lib/ai/anthropicClient.ts` is `claude-opus-4-8` (one line).
- Flip the spec frontmatter `status: draft` -> `status: done`.
- Single commit, conventional-commit message describing the WHY.

## Constraints (hard, from the spec + the suite rules)

- Admin auth verified ONCE at the route boundary via `verifyAdminCookie(request)` (reads from the
  `Request` object). NO `next/headers` cookie reads inside the detached async tool-use loop.
- The agent's removal primitives are `archive_row` / `bulk_archive_rows` (reversible). Hard
  `delete_row` / `bulk_delete_rows` are NOT exposed to the agent.
- `upload_file` returns a loud, structured error ("Image upload requires Storage Brain integration --
  not yet configured") and records nothing. Honest-disabled, never silent success.
- Every mutation tool reads-before-writes for update/archive/status ops; `AgentChange.inversePayload`
  captures the previous state so Undo is exact.
- Errors SURFACE over SSE (`agent:error`), never swallowed; `AgentRun.status` -> `failed` on error.
- SSE client is fetch + `ReadableStream` + a new `parseSseFrames` util (`src/lib/ai/parseSse.ts`). No
  `EventSource`. Route tests mock `getAnthropicClient()` via `vi.mock` (msw is NOT installed).
- Studio design tokens only (no hardcoded gray/blue/red). Reuse `src/components/ui/*`. Keep the CMS grid
  `.light`.
- Production-grade, not gate-passable: cover the unhappy paths the spec lists (auth fail, validation
  fail, CSV size cap, tool error, partial undo). Zero tech debt: any follow-up you notice in-scope, fix
  it in this PR; do NOT leave bare `TODO`s. Use `open_thread` ONLY for genuinely out-of-scope
  pre-existing issues.
- No em-dashes or en-dashes anywhere in code, comments, or commit message.

## Constraints (orchestration)

- Stay in this worktree. Do not modify files outside it. Do not push to any remote (the operator
  handles PR + merge). Do not run destructive commands.
- When done, output a final message confirming the task is complete and listing the files changed.

## Notes

- Deferred items in spec section 1 ("Deferred") are DEFERRED: do NOT half-build image upload, chat
  history persistence, collection groups, streaming partial results, or multi-collection runs. Record
  them as `open_thread` entries if you want them tracked, but the spec already scopes them out.
- `translate_field` / `generate_content` use batched INNER Haiku calls (non-streaming, invisible to the
  SSE stream), per section 2 Option A. The app references `process.env.ANTHROPIC_API_KEY` at run time;
  it does NOT need to be set during this build/verify (tests mock the client).
- The grid re-fetch on `agent:done` reuses the existing `CmsGrid` key-bump signal; wire
  `onRunComplete(runId)` to it, do not invent a new refresh mechanism.
