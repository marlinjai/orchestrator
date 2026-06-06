---
task: arbosano-admin-latency-p3
spec: plans/2026-06-03-admin-edit-latency.md
depends_on: [arbosano-admin-latency-p2]
shared_state: [lockfile]
---

# Goal

Implement Phase 3 of the admin edit latency plan: route simple copy edits to Haiku (faster + cheaper), add legible step-by-step streaming status in the chat UI, and optionally investigate Turbopack for the preview dev server. Phases 1 and 2 must already be merged before this phase starts.

## Read first

- `plans/2026-06-03-admin-edit-latency.md` (the full plan, especially "Phase 3" and "Hard constraints")
- `src/lib/admin/agent.ts` (current `ADMIN_AGENT_MODEL`, `runAgent` signature, the messages loop)
- `src/app/api/admin/chat/route.ts` (POST handler, how `runAgent` is called, what events are streamed)
- `src/app/(admin)/admin/page.tsx` (the chat UI, `sendChat`, the current streaming event handling, the `didMutate` / iframe reload logic)
- `src/lib/worktree-sessions/runner.ts` (`buildNextDevArgv`, the `--webpack` flag and its context)

## What to build

### 3a. Model routing: simple edits to Haiku

In `src/app/api/admin/chat/route.ts` (or in `agent.ts`):

- Add a simple heuristic function `isSimpleCopyEdit(message: string): boolean`. A conservative check: the message is short (under ~120 chars), contains no structural/layout/component keywords (avoid a long blacklist; err on the side of routing to Sonnet on any doubt). Words that suggest a structural change: "component", "section", "layout", "add", "remove", "delete", "create", "build", "refactor", "restructure". Words that suggest a copy edit: just check brevity and absence of structural keywords. Default to `false` (Sonnet) when in doubt.
- Add a `model?` parameter to `runAgent` (default: `ADMIN_AGENT_MODEL` which stays `"claude-sonnet-4-6"`). Pass the chosen model into the `client.messages.create` call.
- In `route.ts`, call `isSimpleCopyEdit(body.message)` and pass `model: "claude-haiku-4-5-20251001"` to `runAgent` when true, else leave the model at the default.
- Keep the routing logic simple and conservative: one wrong route to Haiku is caught by the fences + tsc; the downside is cosmetic noise, not data loss.

### 3b. Legible streaming status in the chat UI

In `src/app/(admin)/admin/page.tsx`:

- The current UI disables the send button while streaming. Add a small, clearly visible status line below the message input that shows the current step. Suggested step labels (in German, matching the operator's language, NO em-dashes):
  - idle: nothing shown
  - "Liest Seite..." -- while discovery or read tool calls are in flight (if they happen at all after Phase 2)
  - "Schreibt Aenderung..." -- when an `edit_file` or `write_file` tool event arrives
  - "Typpruefung..." -- if a tsc event is streamed (optional: if the agent emits a signal for this)
  - "Fertig." -- when the stream closes successfully
  - "Fehler." -- on stream error
- Base these on the NDJSON event stream already coming from the chat route. Map tool-call events to the appropriate label. Keep the implementation simple: a single `statusLine` state string, not a complex step machine.
- The iframe reload already fires on `didMutate` (from PR #39). Do NOT change that logic. The status line is purely informational.

### 3c. (Conditional) Turbopack investigation

Read `src/lib/worktree-sessions/runner.ts` and the git log for `buildNextDevArgv`. The `--webpack` flag was added deliberately (a prior `TURBOPACK=1` env conflict, a "Multiple bundler flags set" boot failure per the plan). If the history is clean and the conflict is no longer present, try switching to Turbopack in `buildNextDevArgv`. If ANY of the following: the history is ambiguous, the conflict is still present, or a test/build failure occurs, leave `--webpack` in place and add an `open_thread` comment in the goal output noting the investigation result. Do NOT break the preview server to gain Turbopack speed -- the plan says render is not the bottleneck anyway.

## Definition of done

- `pnpm test` passes.
- `pnpm build` green (or `pnpm tsc --noEmit` if build needs secrets).
- `pnpm lint` green.
- No em-dashes (U+2014) or en-dashes (U+2013) in any added code, comments, strings, or UI labels.
- `runAgent` accepts an optional `model` parameter and passes it to `messages.create`.
- `isSimpleCopyEdit` exists, is conservative (defaults to `false` / Sonnet), and is tested with at least three cases (short copy edit -> true, "add a new section..." -> false, empty string -> false).
- The chat UI shows a status line with at least the "Schreibt Aenderung..." and "Fertig." states.
- Status line uses German labels with NO em-dashes (use "Aenderung" not "Änderung" if special characters are an issue in the codebase, but prefer the proper umlaut if the codebase already uses German strings elsewhere).
- The iframe reload logic (`didMutate`) is unchanged.
- Single conventional-commit on this branch.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- Do not run destructive commands.
- The model routing heuristic MUST default to Sonnet on any ambiguity. Haiku is only for clearly simple copy edits.
- Do NOT attempt the Turbopack change if there is any sign of the prior `TURBOPACK=1` env conflict or if it causes a test/build failure.
- No em-dashes or en-dashes anywhere: code, comments, commit messages, UI strings.
- When done, output a final message that Phase 3 is complete and note the Turbopack investigation outcome.

## Notes

Phases 1 and 2 must already be merged into main before this worktree is created. Verify with `git log --oneline -5`.

The status line labels are suggestions. If the NDJSON event stream from `route.ts` does not currently emit tool-level events, add a simple `{type:"tool_start",name:...}` event at the start of each tool invocation in `runAgent` so the UI can distinguish them. Keep the server-side changes minimal.
