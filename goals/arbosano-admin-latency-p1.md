---
task: arbosano-admin-latency-p1
spec: plans/2026-06-03-admin-edit-latency.md
shared_state: [lockfile]
---

# Goal

Implement Phase 1 of the admin edit latency plan: add a targeted `edit_file` tool with str_replace semantics to the admin tool runner, extract `validateAndWrite` as a shared helper, and move the tsc check so it no longer delays the operator-visible turn. This is the highest-leverage change: it eliminates the ~47s full-file rewrite by having the model emit only the changed snippet.

## Read first

- `plans/2026-06-03-admin-edit-latency.md` (the full plan, especially the "Phase 1" section and "Hard constraints")
- `src/lib/admin/tools.ts` (the fence chain, `runWriteFile`, `assertWritablePath`, `containsLongDash`, `violatesContentShape`, `createTools`, `TOOL_DEFS`)
- `src/lib/admin/agent.ts` (the tool-use loop, `runAgent`, `ADMIN_AGENT_MODEL`, `MAX_TOKENS_PER_TURN`, `SYSTEM_PROMPT`, the tsc-after-write call)
- `src/app/api/admin/chat/route.ts` (POST handler, how tools are constructed and threaded)
- `src/lib/admin/__tests__/` (existing fence tests, to understand the test pattern)

## What to build

### 1a. Add the `edit_file` tool def in `tools.ts`

Add a new `ToolDef` constant `EDIT_FILE` with:
- name: `edit_file`
- description (write it with NO em-dashes or en-dashes): a clear instruction to use this tool for changes to existing files, provide `path`, `old_str` (exact current text, enough context for a unique match), and `new_str` (the replacement). Note that the same fences run on the full resulting file.
- input_schema: object with required properties `path` (string), `old_str` (string), `new_str` (string). All required.

Add `EDIT_FILE` to the `TOOL_DEFS` array (between `WRITE_FILE` and `LIST_FILES` is fine).

### 1b. Extract `validateAndWrite` helper

Inside `tools.ts`, extract the fence chain that currently lives in `runWriteFile` (from the media-ext check for content scope through the `writeFile` call) into a private helper:

```
async function validateAndWrite(
  fenced,            // the successful assertWritablePath result
  fullContent: string,
  scope: EditScope,
): Promise<ToolResult<WriteFileResult>>
```

Refactor `runWriteFile` to call `validateAndWrite` after `assertWritablePath` so behavior is unchanged. This helper is also called by `runEditFile`.

### 1c. Implement `runEditFile`

Add `async function runEditFile(worktreePath, inputPath, inputOld, inputNew, scope)`:

1. Type-check: `if (typeof inputOld !== "string" || typeof inputNew !== "string") return {ok:false, fence:"input", error:"old_str and new_str must be strings"}`.
2. `const fenced = await assertWritablePath(worktreePath, inputPath, scope); if (!fenced.ok) return fenced;`
3. Read current file: `const current = await readFile(fenced.absPath, "utf8")` (wrap in try/catch, return `{ok:false, fence:"io"}`).
4. Guard empty old_str: `if (inputOld === "") return {ok:false, fence:"input", error:"old_str must be non-empty"}`.
5. Count matches: `const n = current.split(inputOld).length - 1`.
   - zero: return `{ok:false, fence:"edit-nomatch", error:"old_str not found; copy the exact current text including surrounding lines"}`.
   - multiple: return `{ok:false, fence:"edit-ambiguous", error:\`old_str matches ${n} places; add more surrounding context for a unique match\`}`.
6. Compute: `const next = current.replace(inputOld, inputNew)` (single replace, exactly one match).
7. `return validateAndWrite(fenced, next, scope)` -- this runs dash + content-shape + media + write on the FULL resulting file.

Add `case "edit_file":` to `createTools().run` that calls `runEditFile`.

### 1d. Update the system prompt in `agent.ts`

Add a dash-free rule in `SYSTEM_PROMPT` that for changes to EXISTING files the model MUST use `edit_file` with a minimal but uniquely-matching `old_str`, and reserve `write_file` for creating NEW files only. Keep the existing "make the change, do not just describe it" rule.

Also update the tsc call: ensure `runTscDiagnostics()` is triggered for BOTH `write_file` and `edit_file` successes (rename or generalize the `writeSucceeded` / `mutated` tracking variable to cover both). The tsc call itself stays where it is (after the tool loop, before the model's next turn) -- it should NOT be removed or made truly async. The win here is that `edit_file` is tiny, so the turn that calls it finishes in ~1 to 3s instead of ~47s; the tsc that follows is for the model, not the operator. The iframe already reloads on the tool event (via `didMutate` in the existing chat route), so the operator sees the change without waiting for tsc.

### 1e. Tests

Add tests for `edit_file` in the existing test file or a new `tools.edit.test.mts` under `src/lib/admin/__tests__/`. Assertions:

- Exact single match: replaces correctly and writes the full resulting file.
- `edit-nomatch` when `old_str` is not present.
- `edit-ambiguous` when `old_str` appears more than once; error mentions the count.
- Dash fence: `new_str` introducing an em-dash (U+2014) is rejected (fence runs on the full resulting file).
- Content-shape: `new_str` introducing JSX into a `src/content/**` path is rejected.
- Path outside allow set / in a blocked zone is rejected (same as write_file).

Use the fake-worktree pattern already present in the existing fence tests.

## Definition of done

- `pnpm test` passes (all existing tests green, new edit_file tests green).
- `pnpm build` green (or `pnpm tsc --noEmit` if build needs secrets).
- `pnpm lint` green (no new lint errors).
- No em-dashes (U+2014) or en-dashes (U+2013) in any added code, comments, or strings. Use colons, commas, parens, or a new sentence instead.
- The `edit_file` tool appears in the tool defs returned by `createTools()`.
- `runEditFile` calls `validateAndWrite` (not a copy-pasted fence chain).
- The dash and content-shape fences run on the FULL resulting file, not just `new_str`.
- `SYSTEM_PROMPT` instructs the model to prefer `edit_file` for existing files.
- New tests cover all six cases listed above.
- Single conventional-commit on this branch with a message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- Do not run destructive commands.
- The four fences (`assertWritablePath`, dash fence, content-shape fence, media-ext check for content scope) must ALL fire in sequence for every file mutation through both `write_file` and `edit_file`.
- Do not remove or async-fire `runTscDiagnostics()` -- only ensure it fires for both write and edit successes.
- No em-dashes or en-dashes anywhere: code, comments, commit messages. Not even in test fixture strings (use U+2014 as a raw character in a fence-rejection test, but not as prose punctuation in code or comments).
- When done, output a final message that Phase 1 is complete.

## Notes

The plan's "Decisions taken" section is authoritative on what NOT to build: no hosted `str_replace_based_edit_tool` Anthropic type, no dedicated apply model, no removal of tsc. Build exactly what is described, no more.

The plan has a "Hard constraints" section -- read it before writing a line of code.
