---
task: arbosano-phase-2-admin
spec: plans/2026-05-30-phase-2-admin-chat-iframe.md
marlin_proxy: shadow
---

# Goal

Implement arbosano content-as-code **Phase 2**: the `/admin` chat + live iframe + the build-once worktree session manager. You are running inside a git worktree on branch `feat/phase-2-admin`, stacked on `feat/phase-3-1-extractions` (PR #8). Build it to green (lint + tsc + build + the four-fence fixture). Do NOT push, do NOT open a PR, do NOT merge, do NOT deploy. The operator pushes and opens the stacked PR after reviewing your work.

The authoritative spec is `plans/2026-05-30-phase-2-admin-chat-iframe.md`. The condensed build spec, the exact shared contracts, and the verified corrections are in `plans/2026-05-31-cascade-status-phase-2-kickoff.md`. **Read both fully before writing any code.**

## Repo-state precondition

- You are on branch `feat/phase-2-admin` in a worktree, stacked on `feat/phase-3-1-extractions`.
- Working tree must be clean at start. If it is not, escalate.
- These already exist from PR #8 and you MUST reuse them (never recreate, never re-extract):
  - `src/lib/zones.ts` : `CONTENT_GLOBS`, `COMPONENTS_GLOBS`, `BLOCKED_GLOBS` (the role-glob source of truth for Fence 1).
  - `src/lib/dom.ts` : `isTypingTarget`. The spec section 2.0 says to lift `isTypingTarget` from `FeedbackWidget.tsx` into a new `src/lib/is-typing-target.ts`. That is STALE: #8 already extracted it to `src/lib/dom.ts`. Import from `src/lib/dom.ts`. Do NOT create `src/lib/is-typing-target.ts`. Do NOT touch `FeedbackWidget.tsx`.
  - `src/lib/rate-limit.ts` : `checkThrottle(ipHash, {limit, windowMs, bucket})` + `getClientIpHash(req)` (reuse if the chat route needs throttling; single operator, so throttling is optional here).
  - `src/lib/media.ts` : Phase 3 helpers (do NOT touch in Phase 2).

## Read first

- `plans/2026-05-30-phase-2-admin-chat-iframe.md` (full: all four sub-phases, Key components, Reuse, Risks, non-goals).
- `plans/2026-05-31-cascade-status-phase-2-kickoff.md` (the "Phase 2 build spec" + "Verified corrections + contracts to trust" sections are authoritative over the spec where they differ).
- Reuse touchpoints, read before mirroring them:
  - `scripts/dev-secrets.sh` (the NextDevRunner spawns `next dev --webpack` through this).
  - `src/app/api/health/route.ts` (the boot-health poll target).
  - `src/app/api/contact/route.ts` (the creds-missing -> 503 pattern; `escapeHtml`, `getClientIpHash` were private here, now `getClientIpHash` is in `rate-limit.ts`).
  - `src/app/(site-overlay)/layout.tsx` (mirror this for the `(admin)` route-group html shell: own `<html lang="de"><body>`, no Header/Footer/FeedbackWidget).
  - `src/components/PageRenderer.tsx` + the content `types.ts` (the `BlockData` union + the `never` exhaustiveness check: this is the compiler-as-schema for Fence 2).

## Decisions already taken (do NOT re-litigate; list them in your final report so the operator can flag them in the PR)

- Agent edit scope (the Fence-1 allow set) = `CONTENT_GLOBS` + `COMPONENTS_GLOBS` + `src/app/globals.css`. Hard-reject `BLOCKED_GLOBS` unconditionally (blocked always wins over allow). `public/media/**` is Phase 3, NOT in the Phase 2 allow set.
- Worktree base ref for the runtime session manager = `origin/main`.
- `Runner` interface is sized for the Phase 2.5 sidecar: it carries `readonly needsProxy` and `readonly memoryCeilingMb`.
- Agent model = `claude-sonnet-4-6`.

## Build (sub-phase order; contracts are fixed so the modules compose)

You may use subagents for the three file-disjoint clusters (A: auth + UI, B: worktree-sessions, C: agent + tools), but you integrate and verify the result yourself. Build in sub-phase order so each layer has what the next needs.

### Shared contracts (exact signatures, so the clusters compose)

- `src/lib/admin/auth.ts` (Cluster A): `adminEnabled()` returns `process.env.ADMIN_ENABLED === "true" && process.env.NODE_ENV !== "production"`; `adminTokenValid(req)` checks an httpOnly `admin_token` cookie equals `process.env.ADMIN_TOKEN`; `assertAdminApi(req): Promise<Response | null>` returns a 404 when `!adminEnabled()`, a 401/403 on a bad/missing token, else `null`. Header comment: this is a throwaway stopgap replaced wholesale by better-auth in Phase 4.
- `src/lib/worktree-sessions/index.ts` (Cluster B): `getSessionManager()` is a `globalThis`-singleton; `SessionManager` exposes `acquire(key)` (resume-or-provision, idempotent), `get(key)`, `release(key)`, `stats()`. `Session = { key, branch, worktreePath, port, status }`. One active session, fixed port 3100, in-memory `byKey` Map, branch `staging/admin/<timestamp computed lazily inside acquire()>`.
- `src/lib/worktree-sessions/runner.ts` (Cluster B): the `Runner` interface (`spawn({worktreePath, port, env})`, `healthcheck(handle)`, `stop(handle, grace)`, `readonly needsProxy`, `readonly memoryCeilingMb`) + `NextDevRunner` (`needsProxy=false`, `memoryCeilingMb=1024`). Leave a documented seam for a future `ClaudeWorkerRunner` and a proxy-needing runner.
- `src/lib/admin/tools.ts` (Cluster C): `createTools(worktreePath): { defs, run }`.

### Cluster A: the `(admin)` route group + two-pane shell + stopgap auth (sub-phase 2.0)

- `src/lib/admin/auth.ts` (contract above).
- `src/app/(admin)/layout.tsx`: own `<html lang="de"><body>`, `import "../globals.css"`, NO Header/Footer/FeedbackWidget, `notFound()` when `!adminEnabled()`. Mirror `src/app/(site-overlay)/layout.tsx`.
- `src/app/(admin)/admin/page.tsx`: two-pane client shell, chat left (~40%) + `<iframe>` right (~60%). On mount POST `/api/admin/session`, set `iframe.src` to `http://localhost:<port>` from the response. The composer streams NDJSON from POST `/api/admin/chat`. A Publish button. Handle 503 (creds missing) and the paste-token form. Reuse `isTypingTarget` from `src/lib/dom.ts`.

### Cluster B: the build-once worktree session manager (sub-phase 2.1, the keystone)

- `src/lib/worktree-sessions/port.ts`: bind-probe a port before spawn.
- `src/lib/worktree-sessions/git.ts`: `provisionWorktree` = `git worktree add -b <branch> <path> origin/main` then `pnpm install --frozen-lockfile --offline` (shared store makes it near-free); `removeWorktree` = `git worktree remove --force` + `git worktree prune`.
- `src/lib/worktree-sessions/runner.ts`: `NextDevRunner.spawn` execs `bash scripts/dev-secrets.sh next dev --webpack -H 127.0.0.1 -p <port>` with cwd = worktree and `NODE_OPTIONS=--max-old-space-size=1024` on the child. **`--webpack` is LOAD-BEARING and must NEVER be Turbopack: webpack is ~1 to 3GB RSS, Turbopack is 7GB+ and OOMs the shared box. Unit-test that the spawned argv contains `--webpack`.** `healthcheck` polls `http://127.0.0.1:<port>/api/health` until 200 or 60s. `stop` = SIGTERM then SIGKILL after grace.
- `src/lib/worktree-sessions/index.ts` (contract above).
- `src/app/api/admin/session/route.ts`: `export const runtime = "nodejs"`, `export const dynamic = "force-dynamic"`. Call `assertAdminApi(req)` first (return early if non-null), then `getSessionManager().acquire("default")`, return `{ port, status }`.

### Cluster C: the agent loop + four independent fences (sub-phases 2.2 + 2.3, most security-critical)

- Deps (the ONLY new deps; this is the one human-gated package.json/lockfile edit that IS in scope): `pnpm add @anthropic-ai/sdk picomatch && pnpm add -D @types/picomatch`.
- `src/lib/admin/tools.ts`: `createTools(worktreePath)` exposing read_file / write_file / list_files / commit_changes, with FOUR FENCES, each failing closed:
  1. **In-process (before any I/O):** reject absolute paths; resolve against `worktreePath` and reject anything not contained under the RESOLVED real path (defeats `../`); realpath every path component (defeats symlink escape); role-glob via `picomatch` against the imported `src/lib/zones.ts` constants (ALLOW `CONTENT_GLOBS` + `COMPONENTS_GLOBS` + `src/app/globals.css`; HARD-REJECT `BLOCKED_GLOBS`; blocked wins); a **dash fence** rejecting any U+2014 or U+2013 in written content; a **content-shape fence** keeping `src/content/**` writes string / string-array shaped, never JSX.
  2. **Compiler-as-schema:** after a write, run `tsc --noEmit` in the worktree and feed the diagnostics back into the agent turn.
  3. **OS/git isolation:** operate only inside `worktreePath`; the agent has no handle to `main` or another session.
  4. **CI:** the Phase 5 path-scoped gate (out of scope here; in Phase 2 the human is the reviewer).
- `src/lib/admin/git-identity.ts`: the admin git author identity; dash-safe commit-message construction; `gh pr create --base main` helper for the Publish flow. **It NEVER merges.**
- `src/lib/admin/agent.ts`: a custom server-side Messages-API tool-use loop (NOT Managed Agents), model `claude-sonnet-4-6`, streaming NDJSON events `{type: "text" | "tool" | "error" | "done"}`, reading the key from `process.env.ANTHROPIC_API_KEY` server-side only.
- `src/app/api/admin/chat/route.ts`: `runtime = "nodejs"`, `dynamic = "force-dynamic"`. `assertAdminApi(req)` first; 503 if no `ANTHROPIC_API_KEY` (contact-route pattern); 409 if no active session; otherwise stream `application/x-ndjson`.
- The Publish button in `admin/page.tsx` drives `commit_changes` + the `gh pr create --base main` helper. Phase 2 merge is BY HAND (operator). The session manager is NEVER the merge actor.

## Definition of done

- `pnpm exec eslint --max-warnings=0 .` passes.
- `pnpm exec tsc --noEmit` passes.
- `pnpm build` passes.
- The unit test asserting the NextDevRunner argv contains `--webpack` passes.
- **The four-fence fixture passes.** Write a throwaway fixture (a `.mts` run via `node --experimental-strip-types`, mirroring the media fixture pattern referenced in the handover) that drives `createTools(tmpWorktree).run` and asserts: write_file REJECTS (a) an absolute path, (b) a `../` escape, (c) `next.config.ts` (blocked-glob), (d) em-dash content, (e) JSX in a `src/content/**` write; write_file ALLOWS a plain string edit under `src/content/**`; and that a tsc diagnostic from a bad write flows back into the result. This fixture is the security gate: if any assertion cannot be made to pass honestly, escalate.
- Commits on `feat/phase-2-admin` with conventional-commit messages describing the WHY, dash-safe. One commit per sub-phase is fine.
- Call `update_state(kind="commit")` immediately after each `git commit`; `update_state(kind="file_touched")` for each new file; `update_state(kind="decision")` for each non-obvious choice; `update_state(kind="open_thread")` for: (1) the deferred live `:3100` session-manager boot (operator runs it), and (2) Marlin's Infisical dev-scope actions: add `ANTHROPIC_API_KEY` (dev only, never prod, never browser), `ADMIN_ENABLED=true`, `ADMIN_TOKEN=<value>`.
- Final message: a summary listing the decisions-taken above, the files added, the deps added, the open threads, and confirmation that lint + tsc + build + the four-fence fixture are green.

## Constraints

- Stay inside this worktree. Do not modify any file outside it.
- Do NOT push to any remote. Do NOT open a PR. Do NOT merge. Do NOT deploy. Do NOT run the live `next dev` / `:3100` session-manager boot (the operator runs that during verification, to avoid orphaned worktrees and dev servers). You may run `tsc`, `eslint`, `pnpm build`, and the four-fence fixture.
- No em-dashes (U+2014) and no en-dashes (U+2013) anywhere: code, comments, strings, commit messages. The Phase 5 dash-guard rejects added long dashes. Use colons, parentheses, commas, or new sentences.
- Your OWN edits must also respect the never-auto-merge set: do not touch `next.config.*`, `Dockerfile`, `entrypoint.sh`, `infra/**`, `.github/**`, `eslint.config.*`, `tsconfig.json`, or anything auth/secrets, EXCEPT the in-scope `package.json` + `pnpm-lock.yaml` change for the two declared deps.
- `ANTHROPIC_API_KEY` is server-side and dev-only: reference `process.env.ANTHROPIC_API_KEY`, never hardcode it, never expose it to the browser bundle. Secrets come from Infisical only.
- ~7 to 8 new files + 2 runtime deps (+ 1 dev dep) is the expected footprint. Material scope beyond that is an escalation.

## Escalation rules

- Working tree not clean at start: stop, escalate.
- Any of the four fences cannot be made to fail closed honestly: escalate (do not ship a weakened fence).
- The installed `@anthropic-ai/sdk` version's tool-use loop shape is ambiguous and you would have to guess the API: escalate rather than guess.
- Scope creep beyond the ~8 files + the 2/1 deps: escalate.
- `pnpm build` or `tsc` fails for a reason you cannot resolve inside the worktree without touching a blocked file: escalate.

## Out of scope (stated, not parked)

- The live `:3100` session-manager boot (operator-run verification).
- Phase 3 media: the `public/media/**` allow-glob, `POST /api/admin/media`, client paste/drop. That is the next PR.
- better-auth (Phase 4), the publish-pipeline MERGE_TOKEN GitHub App + GitHub Team (Phase 5).
- Any push, PR, merge, or deploy. The operator handles the stacked PR; Marlin merges the cascade by hand.
