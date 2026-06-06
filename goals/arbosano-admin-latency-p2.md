---
task: arbosano-admin-latency-p2
spec: plans/2026-06-03-admin-edit-latency.md
depends_on: [arbosano-admin-latency-p1]
shared_state: [lockfile]
---

# Goal

Implement Phase 2 of the admin edit latency plan: inject the target route and current content file up front (eliminating the `list_files` + `read_file` discovery round-trips), and add prompt caching on the stable system-prompt + tool-defs prefix. Phase 1 (the `edit_file` tool) must already be merged before this phase starts.

## Read first

- `plans/2026-06-03-admin-edit-latency.md` (the full plan, especially "Phase 2" section and "Hard constraints")
- `src/lib/admin/tools.ts` (the full createTools signature and tool defs, now including `edit_file` from Phase 1)
- `src/lib/admin/agent.ts` (the `runAgent` function, `SYSTEM_PROMPT`, `client.messages.create` call, usage fields)
- `src/app/api/admin/chat/route.ts` (POST handler, how body is parsed, how tools are constructed, how conversation is threaded)
- `src/app/(admin)/admin/page.tsx` (the chat UI, `sendChat`, how it POSTs to the chat route)
- `src/app/(site)/[slug]/page.tsx` (how slugs resolve to content modules, to mirror the route-to-file map)
- `src/content/pages/` (list the files to understand the full set of content file paths)

## What to build

### 2a. Route-to-content-file map

Create `src/lib/admin/content-routes.ts` that exports a `Record<string, string>` mapping URL routes to content file paths relative to the repo root. Examples: `"/" -> "src/content/pages/home.ts"`, `"/baumpflege" -> "src/content/pages/baumpflege.ts"`, etc. Derive the mapping by reading how `src/app/(site)/[slug]/page.tsx` resolves slugs -- do NOT hardcode blindly; confirm the actual file names in `src/content/pages/`. Cover all pages in that directory. The `/` route maps to the home page content file.

### 2b. Inject route + current file contents into the conversation (transient, not persisted)

In `src/app/api/admin/chat/route.ts`:

- Accept an optional `route` field in the parsed request body (string, default to `"/"`).
- After parsing the body but before calling `runAgent`, resolve `route` via the content-routes map to a file path. Read that file's current contents from the worktree path. If the route is not in the map or the file cannot be read, skip injection gracefully (log server-side, do not throw).
- Build a transient context string (NO em-dashes or en-dashes): "The operator is currently viewing route `<route>`, rendered from `<contentFilePath>`. Its current contents are below. Prefer editing this file using edit_file. <fenced file contents (use triple-backtick with the file extension as language tag)>".
- Inject this as an additional user message prepended to the conversation for THIS turn only. Do NOT append it to the stored conversation (the `messages` array managed by `src/lib/admin/conversation.ts`). Pass the augmented messages to `runAgent`, but persist only the original messages.

### 2c. Send `route` from the UI

In `src/app/(admin)/admin/page.tsx`:

- In `sendChat`, include `route: "/"` in the POST body for now. (The true current route of the preview iframe is cross-origin and requires a `postMessage` bridge; that is deferred. Sending the default route removes discovery for the most common home-page editing case and the operator's text disambiguates for other pages.)

### 2d. Update system prompt

In `src/lib/admin/agent.ts`, add a dash-free rule to `SYSTEM_PROMPT`: "You are given the current page's content file up front. Do not call list_files or read_file unless the injected file is clearly not the right one for the request."

### 2e. Prompt caching

In `src/lib/admin/agent.ts`, in the `client.messages.create` call:

- Convert the `system` field from a plain string to an array of one content block: `[{type: "text", text: SYSTEM_PROMPT, cache_control: {type: "ephemeral"}}]`. This marks the system prompt as cacheable.
- In the `sdkTools` array (the tool defs passed to the API), add `cache_control: {type: "ephemeral"}` to the LAST tool in the array. Anthropic caches system prompt + tools as a unit for tool-use loops.
- The injected file content (from 2b) is passed as a transient message; mark it cacheable too by setting `cache_control: {type: "ephemeral"}` on that message block. The volatile tail (the operator message + tool results) must NOT be cached.
- Add server-side logging of `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens` from the `messages.create` response to confirm cache hits during verification. Never log these to the browser.

## Definition of done

- `pnpm test` passes.
- `pnpm build` green (or `pnpm tsc --noEmit` if build needs env secrets).
- `pnpm lint` green.
- No em-dashes (U+2014) or en-dashes (U+2013) in any added code, comments, or strings.
- `src/lib/admin/content-routes.ts` covers all pages in `src/content/pages/` including `/` (home).
- The chat route reads and injects the content file transiently -- the stored conversation is NOT modified.
- `system` in `messages.create` is now an array with `cache_control: ephemeral` on the last block.
- `cache_control: ephemeral` is set on the last tool def in `sdkTools`.
- `cache_control: ephemeral` is set on the injected file-content message block.
- Server-side logs emit `cache_creation_input_tokens` and `cache_read_input_tokens` for verification.
- Single conventional-commit on this branch.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- Do not run destructive commands.
- The transient injection must NOT be appended to the persistent conversation store. Injecting it into the conversation for a single turn only is the explicit requirement.
- Route resolution must fail gracefully (log + skip, never throw) when a route is not in the map.
- No em-dashes or en-dashes anywhere: code, comments, commit messages.
- When done, output a final message that Phase 2 is complete.

## Notes

Phase 1 (the `edit_file` tool) must already be merged into main before this worktree is created. Verify with `git log --oneline -5` that the `edit_file`-related commit is present.

The injected file content is intentionally NOT stored in the conversation history. The stored conversation must remain tool-call + text only, as managed by `src/lib/admin/conversation.ts`.
