---
task: arbosano-phase-2-5-editscope
spec: plans/2026-05-31-phase-2-5-hosted-admin-executor.md
marlin_proxy: shadow
---

# Goal

Implement arbosano **Phase 2.5 sub-phase 2.5.0 ONLY**: the per-session `EditScope` and the secret-starved preview env. This is the KEYSTONE security fix that makes a hosted, multi-user `/admin` safe. You run inside a git worktree on branch `feat/phase-2-5-editscope` off `main` (which already has Phase 4 better-auth + Phase 5 merged). Build to green with a fixture that proves the hosted scope refuses code writes. Do NOT build 2.5.1 to 2.5.4. Do NOT push, open a PR, merge, or deploy. The operator reviews + runs the live localhost boot + opens the PR.

The authoritative spec is `plans/2026-05-31-phase-2-5-hosted-admin-executor.md`. **Read it fully, especially "The keystone finding" and sub-phase 2.5.0, before writing any code.**

## The finding this fixes (read first)

A live preview `next dev` server EXECUTES whatever code the agent writes. Today the agent's allow-set is `CONTENT_GLOBS + COMPONENTS_GLOBS + globals.css`, and `COMPONENTS_GLOBS` includes `src/app/**` + `src/lib/**`. On localhost (single operator, Marlin is the reviewer) that is fine. Hosted-multi-user it is a remote-code-execution path: an authed editor, or the agent via prompt-injection in page copy it reads, writes `src/app/api/x/route.ts` returning `process.env`, the preview serves it, and whatever secrets that process carries leak. Two independent mitigations, do BOTH.

## Repo-state precondition

- Branch `feat/phase-2-5-editscope` in a worktree off `main` (HEAD has Phase 4 + Phase 5). Clean tree at start or escalate.
- Reuse, never recreate:
  - `src/lib/admin/tools.ts`: `createTools(worktreePath)`, the four fences, the allow-set built from `CONTENT_GLOBS + COMPONENTS_GLOBS + PHASE_2_EXTRA_ALLOW`, the `AGENT_MACHINERY_GLOBS` block, `blockedMatch`/`machineryMatch`/`allowMatch`. This is what you parameterize.
  - `src/lib/zones.ts`: `CONTENT_GLOBS`, `COMPONENTS_GLOBS`, `BLOCKED_GLOBS`. IMPORT, do not edit.
  - `src/lib/worktree-sessions/index.ts`: `SessionManager` + `SessionManagerOptions`. You add an `editScope` option.
  - `src/lib/worktree-sessions/runner.ts`: `NextDevRunner` spawns `bash scripts/dev-secrets.sh next dev --webpack ...`. The hosted preview will spawn through a new secret-starved script.
  - `scripts/dev-secrets.sh`: the template for `dev-secrets-preview.sh` (read it to mirror its shape).
  - `src/app/api/admin/chat/route.ts`: calls `createTools(session.worktreePath)`. You thread the scope here.
  - `src/lib/admin/__tests__/tools.fence.test.mts`: the existing fence fixture. It MUST still pass unchanged (it exercises the default = localhost scope).

## Build (2.5.0 only)

### Mitigation 1: the EditScope on the allow-set
- Add `export type EditScope = "localhost" | "hosted";` (in `tools.ts` or a small shared spot).
- `createTools(worktreePath, scope: EditScope = "localhost")`: the DEFAULT is `localhost`, which keeps TODAY'S allow-set exactly (`CONTENT_GLOBS + COMPONENTS_GLOBS + globals.css`), so every existing call site and the localhost flow are byte-unchanged.
- `scope === "hosted"` collapses the allow-set to **content + media + globals only**: `CONTENT_GLOBS` (which already includes `src/content/**`, `public/media/**`, `public/photos/**`) + `src/app/globals.css`. NO `COMPONENTS_GLOBS` (no `src/app/**`, no `src/lib/**`, no `src/components/**`).
- ALL other fences are unchanged in BOTH scopes: path-containment/realpath, the `BLOCKED_GLOBS` hard-reject, the `AGENT_MACHINERY_GLOBS` hard-reject, the dash fence, the content-shape fence. `hosted` only SHRINKS the allow set; it never widens or relaxes anything.
- Thread the scope from the `SessionManager` (a new `editScope?: EditScope` in `SessionManagerOptions`, default `localhost`) through to `createTools` at the `chat` route call site (`createTools(session.worktreePath, mgr.editScope())` or equivalent; expose the manager's scope).

### Mitigation 2: the secret-starved preview env
- Add `scripts/dev-secrets-preview.sh`: a sibling of `dev-secrets.sh` that runs `next dev` with a MINIMAL env and NO Infisical dev scope. The preview child must NOT receive `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, the real `DATABASE_URL`, or the real `BETTER_AUTH_SECRET`. Provide only what `next dev` needs to render the site (a dummy `BETTER_AUTH_SECRET`, `NODE_ENV`, `PORT`/host args passed through). Mirror `dev-secrets.sh`'s arg-passthrough shape (it execs `next dev --webpack -H ... -p ...`). Document at the top WHY (the preview executes agent code, so it must carry nothing worth stealing). shellcheck-clean.
- Wire selection: the spawn script is chosen by scope. For `hosted`, the runner spawns through `dev-secrets-preview.sh`; for `localhost`, it keeps `dev-secrets.sh` (unchanged). Keep this minimal: a scope-aware script path in the spawn argv (extend `buildNextDevArgv` or the runner to take the script name), with the localhost default unchanged. The `--webpack` flag stays LOAD-BEARING in both (never Turbopack); keep the existing argv unit test green.

## Definition of done

- `pnpm exec eslint --max-warnings=0 .`, `pnpm exec tsc --noEmit`, `pnpm build`: green.
- `pnpm test` STILL passes: the existing `tools.fence.test.mts` (default/localhost scope) is unchanged-behavior, and the `runner.test.mts` argv test (still asserts `--webpack`) passes.
- A NEW fixture (mirror the `.mts` + tools-loader pattern) `tools.editscope.test.mts` proving, with `createTools(tmpWorktree, "hosted")`:
  - REJECTS (fence1-glob) a write to `src/app/page.tsx`, `src/app/api/x/route.ts`, `src/lib/foo.ts`, and `src/components/Bar.tsx`.
  - ALLOWS a write to `src/content/pages/baumpflege.ts`, `public/media/abcd1234.webp` (shape permitting), and `src/app/globals.css`.
  - AND with `createTools(tmpWorktree, "localhost")` (and the no-arg default): `src/components/Bar.tsx` is ALLOWED (proving the localhost scope is unchanged and the default is localhost).
- `scripts/dev-secrets-preview.sh` exists, is shellcheck-clean, passes through the `next dev` args, and injects NO real secret (grep it: no Infisical dev-scope load, no `ANTHROPIC_API_KEY`/`RESEND`/real DB).
- `update_state(kind="commit"/"file_touched"/"decision")` as you go; `kind="open_thread"` for: (1) 2.5.1 (byAdmin sessions + dynamic ports + concurrency cap + idle reap), (2) 2.5.2 (the preview proxy, needs the host), (3) 2.5.3 (the better-auth gate swap, needs dev auth + the deployment model), (4) 2.5.4 (deploy the admin instance), (5) the hosted runner actually selecting `dev-secrets-preview.sh` is wired but only exercised once a hosted Runner exists (2.5.1/2.5.2).
- Conventional-commit messages, dash-free. Final message: decisions, files, the fixture proof, open threads, confirmation lint+tsc+build+test green.

## Constraints

- Stay in this worktree. No push, PR, merge, or deploy.
- **The localhost flow must stay byte-unchanged.** The default scope is `localhost` = today's exact behavior; every existing call site keeps working with no change required beyond the new optional arg.
- Do NOT build 2.5.1 to 2.5.4 (session-manager generalization, preview proxy, auth-gate swap, deploy). They are coupled to the host / dev-auth and are separate chunks. Touching them is an escalation.
- Do NOT edit `zones.ts` (import it), `auth*.ts`, `next.config.*`, `Dockerfile`, `entrypoint.sh`, `.github/**`, `infra/**`.
- No em-dashes (U+2014) or en-dashes (U+2013) anywhere.
- Expected footprint: `tools.ts` (the scope param + the hosted allow-set), `worktree-sessions/index.ts` (the option), `runner.ts` (scope-aware spawn script, minimal), `chat/route.ts` (pass the scope), `scripts/dev-secrets-preview.sh` (new), `tools.editscope.test.mts` (new). ~6 files. Material scope beyond that is an escalation.

## Escalation rules

- Clean-tree precondition fails: escalate.
- The EditScope change cannot keep the existing `tools.fence.test.mts` passing unchanged (localhost behavior must not regress): escalate.
- Any fence would have to be weakened to make `hosted` work: escalate (hosted only SHRINKS the allow set).
- Scope creep into 2.5.1 to 2.5.4 or any blocked file: escalate.

## Out of scope (stated, not parked)

- 2.5.1 (per-admin sessions, dynamic ports, concurrency cap, idle reap), 2.5.2 (preview reverse-proxy, needs the host), 2.5.3 (the `adminEnabled()` -> better-auth gate swap, needs dev auth + the deployment model), 2.5.4 (deploy the admin instance). Separate chunks.
- The executor host, subdomains, TLS: Marlin's infra.
- Any push, PR, merge, or deploy.
