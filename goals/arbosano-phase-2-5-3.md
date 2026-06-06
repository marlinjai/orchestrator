---
task: arbosano-phase-2-5-3
spec: plans/2026-06-01-handover-phase-2-5-resume.md
marlin_proxy: shadow
---

# Goal

Implement arbosano **Phase 2.5 sub-phase 2.5.3 ONLY**: swap the Phase 2 stopgap admin gate
for the real one (a deployment flag + a better-auth session), **decouple the preview
secret-starve from the agent edit-scope**, wire **per-admin commit attribution + a publish
audit row**, and add a **dev-auth local-login path** so the new gate is testable on localhost.

You run inside a git worktree on branch `feat/phase-2-5-3-auth-gate` off `main` (which already
has Phase 4 better-auth, Phase 5, and the merged 2.5.0 EditScope + secret-starved preview and
2.5.1 multi-session SessionManager). Build to green with tests. **Do NOT push, open a PR,
merge, or deploy.** The operator reviews the diff, runs the live localhost boot you are told
to skip, fixes findings, and opens the PR.

This is pure application code, host-independent. Do **NOT** build 2.5.2 (preview proxy) or 2.5.4
(host deploy + egress lockdown). Do **NOT** touch `infra/**`, `.github/**`, the `Dockerfile`,
`deploy.yml`, or any Infisical/Terraform config. Do **NOT** set `ADMIN_DEPLOYMENT=true` anywhere
in committed config (see the HARD GATE below).

## The one idea behind 2.5.3: decouple three concepts that 2.5.0/2.5.1 conflated into one flag

Today a single notion (`scope === "hosted"` on the SessionManager, and `adminEnabled()` =
`ADMIN_ENABLED && NODE_ENV !== "production"`) drives THREE unrelated things. Split them into
three orthogonal signals:

| Concept | What it controls | Correct signal after 2.5.3 |
|---|---|---|
| **A. Surface exists** | Does `/admin` render + do `/api/admin/*` routes respond at all? | `ADMIN_DEPLOYMENT === "true"` (a pure deployment flag, NODE_ENV-independent so it can run under `next start` on the hosted box AND under `next dev` on localhost) |
| **B. Preview secret-starve + idle-reaping** | Is the per-session `next dev` child spawned secret-starved, and are idle sessions reaped? | **the hosted executor box**, i.e. `ADMIN_DEPLOYMENT === "true" && NODE_ENV === "production"` (a derived predicate `isHostedExecutor()`). NOT the edit-scope. |
| **C. Agent edit-scope** | What files may the agent WRITE in the worktree (`createTools` allow-set)? | the logged-in **user's ROLE** (`editScopeForRole(role)`), NOT the deployment. Default = full for every current role. |

Why B keys off `ADMIN_DEPLOYMENT && NODE_ENV==="production"` and not bare `ADMIN_DEPLOYMENT`:
localhost dev sets `ADMIN_DEPLOYMENT=true` (so the gate + login are testable), but localhost is a
single trusted operator running `next dev` (development). The 2.5.1 hard guarantee is that
localhost **never reaps** and the localhost preview inherits the **full** dev env (byte-unchanged
from Phase 2). The hosted box runs `next start` (production). So `NODE_ENV==="production"` is
exactly what distinguishes "the untrusted multi-user executor" from "localhost dev", with zero
extra env vars. Document this predicate in code.

## HARD GATE (do not violate, and call it out in your final summary)

`ADMIN_DEPLOYMENT` must remain **UNSET in production** until Phase 2.5.4 ships OS isolation +
the outbound-egress lockdown (executed preview content can still phone home / read host files
even with the env scrubbed). So:
- This chunk lands the CODE only. It must NOT set `ADMIN_DEPLOYMENT=true` in any committed file,
  any `deploy.yml`, any Dockerfile, any Infisical reference, or `.env.example` for prod.
- The public prod site keeps `ADMIN_DEPLOYMENT` unset, so `/admin` stays 404 there (the surface
  gate). Merging 2.5.3 must be **public-site-safe**: prod `/admin` still 404, public pages
  unchanged. Verify your reasoning and state it.
- Localhost gets `ADMIN_DEPLOYMENT=true` in the **dev** scope only (the operator sets it in
  Infisical /dev + `.env.example` may document it as a dev key). That is the only place it is on.

## Read first (do not recreate any of this)

- `plans/2026-06-01-handover-phase-2-5-resume.md` (the "NEXT: 2.5.3" section is your spec).
- `src/lib/admin/auth.ts` — the stopgap gate you replace (`adminEnabled`, `adminTokenValid`,
  `tokensMatch`, `assertAdminApi`, the cookie helpers, `ADMIN_TOKEN`/`ADMIN_ENABLED`).
- `src/lib/auth-session.ts` — Phase 4 primitives you build ON: `getAdminSession(headers)`,
  `requireRole(session, zone, action)`, `worktreeKeyForUser({email, sessionId})`,
  `recordAudit(entry)`, the `AdminSession` interface.
- `src/lib/auth-roles.ts` — roles (`editor`, `superadmin`), `RoleName`. Both roles have
  `content:["edit","publish"]`.
- `src/lib/admin/tools.ts` — `createTools(worktreePath, scope)`, `EditScope` (today
  `"localhost" | "hosted"`), the allow-set + the hosted read/list/public-media narrowing.
- `src/lib/worktree-sessions/index.ts` — `SessionManager`: the `scope`/`editScope()`/
  `SessionEditScope` you remove, and `provision()`'s `const hosted = this.scope === "hosted"`
  secret-starve selection + `reapIdle()`'s `if (this.scope !== "hosted") return` you rewrite.
- `src/lib/worktree-sessions/runner.ts` — `RunnerSpawnArgs.scrubEnv` + `secretsScript`,
  `PREVIEW_SECRETS_SCRIPT`, `buildChildEnv`/`PREVIEW_ENV_ALLOWLIST`. **Do not change the scrub
  mechanism**; only change WHO decides to turn it on (the manager).
- `src/lib/admin/git-identity.ts` — `commitAll` (fixed `ADMIN_AUTHOR_*` identity today),
  `openPullRequest`, the dash-guard.
- The four routes: `src/app/api/admin/{session,chat,publish,media}/route.ts` — all call
  `assertAdminApi(req)` and use the constant `"default"` session key.
- `src/app/(admin)/layout.tsx` (calls `adminEnabled()`), `src/app/(admin)/admin/page.tsx`
  (the paste-token form), `src/app/api/admin/login/route.ts` (the paste-token login),
  `src/app/api/auth/[...all]/route.ts` (better-auth's HTTP surface, already mounted).
- `scripts/seed-superadmin.ts`, `scripts/migrate.ts`, `scripts/dev-secrets.sh`, `package.json`.
- The tests: `src/lib/admin/__tests__/auth.gate.test.mts`,
  `src/lib/admin/__tests__/tools.editscope.test.mts`,
  `src/lib/worktree-sessions/__tests__/manager.test.mts`.

## Build

### 1. The gate (`src/lib/admin/auth.ts` + call sites)

Replace the stopgap wholesale:
- Delete `adminEnabled`, `adminTokenValid`, `tokensMatch`, `getAdminTokenCookieName`, the
  `getCookie` helper, the `TOKEN_COOKIE_NAME` const, and all `ADMIN_TOKEN`/`ADMIN_ENABLED`
  references.
- Add `export function adminDeploymentEnabled(): boolean` -> `process.env.ADMIN_DEPLOYMENT === "true"`.
- Add `export function isHostedExecutor(): boolean` -> `adminDeploymentEnabled() && process.env.NODE_ENV === "production"`. (This is signal B; the SessionManager imports it OR derives the same predicate. Put it where both `auth.ts` and the manager can use it without a cycle: if importing `lib/admin/auth.ts` from `worktree-sessions` would create an architectural cross-layer import, define `isHostedExecutor()` in a tiny neutral module, e.g. `src/lib/admin/deployment.ts`, and import it from both. Choose the seam that avoids `worktree-sessions` importing `admin/*`; the existing code deliberately keeps that boundary, see the `SessionEditScope` comment in index.ts.)
- Replace `assertAdminApi` with a function that ALSO returns the session so callers can attribute
  work without re-fetching:
  ```
  export async function requireAdminSession(
    req: Request,
    getSession: (h: Headers) => Promise<AdminSession | null> = getAdminSession,
  ): Promise<AdminSession | Response>
  ```
  Ladder: 404 if `!adminDeploymentEnabled()`; else read `getSession(new Headers(req.headers))`;
  401 if null; 403 if `!requireRole(session, "content", "edit")`; else return the session. The
  injected `getSession` default is `getAdminSession`; the parameter exists so the unit test can
  stub it WITHOUT a DB (mirror the existing test-seam pattern, e.g. `worktreeOps` injection in
  the manager).
- Every route changes from `const denied = await assertAdminApi(req); if (denied) return denied;`
  to `const gate = await requireAdminSession(req); if (gate instanceof Response) return gate;
  const session = gate;` and then uses `session`.

### 2. The per-request session key + identity helpers (`src/lib/auth-session.ts`)

Add three small exports so all four routes derive identical values (single source of truth, no
drift):
- `export function adminSessionKey(session: AdminSession): string` ->
  `worktreeKeyForUser({ email: session.user.email, sessionId: session.session.id })`.
- `export function editorIdentity(session: AdminSession): { name: string; email: string }` ->
  `{ name: session.user.name ?? session.user.email, email: session.user.email }`.
- `export function editScopeForRole(role: RoleName | null): EditScope` -> at launch
  `superadmin -> full`, `editor -> full`, anything else -> `content` (defensive most-restrictive
  default). This map is the ONE knob to tighten a role to content-only later. Import the
  `EditScope` type from `admin/tools.ts` (auth-session.ts may import admin/tools — the forbidden
  direction is worktree-sessions importing admin/*, not auth-session importing it; verify there's
  no import cycle and if there is, put `editScopeForRole` in `admin/tools.ts` instead).

### 3. Decouple the secret-starve + reaping from edit-scope (`src/lib/worktree-sessions/index.ts`)

- Remove `SessionEditScope`, `DEFAULT_EDIT_SCOPE`, the `editScope?` option, the `scope` field,
  and the `editScope()` method. The manager no longer knows about edit-scope at all.
- Add a `hostedExecutor?: boolean` option (default = `isHostedExecutor()` from env, via the
  neutral module from step 1) and a private `hostedExecutor` boolean field.
- `provision()`: `const starve = this.hostedExecutor;` then
  `secretsScript: starve ? PREVIEW_SECRETS_SCRIPT : DEFAULT_SECRETS_SCRIPT, scrubEnv: starve`.
  (Identical mechanism to today; only the DECIDER changed from `this.scope === "hosted"` to the
  deployment predicate.)
- `reapIdle()`: gate on `if (!this.hostedExecutor) return;` (was `if (this.scope !== "hosted")`).
  The localhost guarantee is preserved because localhost is `next dev` -> NODE_ENV development ->
  `isHostedExecutor()` false -> never reaps, full env. State this in the JSDoc.

### 4. Wire the routes to the per-admin key + scope (`src/app/api/admin/*`)

For all four routes, after the `requireAdminSession` gate, compute
`const key = adminSessionKey(session);` and use `key` everywhere the constant `"default"` is
used today (`acquire(key)`, `get(key)`, `release(key)`, `markBusy(key)`/`markIdle(key)`).
- **chat**: `const scope = editScopeForRole(session.user.role);` then
  `createTools(s.worktreePath, scope, editorIdentity(session))` (see step 5 for the new
  `createTools` 3rd arg). Keep the 503-when-`ANTHROPIC_API_KEY`-missing and 409-when-not-ready.
- **publish**: commit with the editor's identity (step 5) and write an audit row (step 6).
- **session** (POST/GET/DELETE) + **media**: just swap `"default"` -> `key`.

### 5. Per-admin commit attribution (`src/lib/admin/git-identity.ts` + `tools.ts` + publish route)

- `commitAll` gains an optional `author?: { name: string; email: string }`. When provided, set
  `GIT_AUTHOR_NAME/EMAIL` + `GIT_COMMITTER_NAME/EMAIL` from it; else fall back to the existing
  fixed `ADMIN_AUTHOR_*` (so localhost / no-session callers are unchanged). Do NOT modify git
  config files; keep the env-var approach.
- `createTools(worktreePath, scope?, author?)`: thread an optional `author` through to
  `runCommit` -> `commitAll({ worktreePath, message, author })`, so the agent's own
  `commit_changes` tool also attributes to the editor. Default author undefined = fixed admin
  identity (localhost back-compat).
- The publish route passes `editorIdentity(session)` to `commitAll`.

### 6. Publish audit row (publish route + a small helper in `git-identity.ts`)

- Add `export async function diffPaths(worktreePath: string, base = "origin/main"): Promise<string[]>`
  -> `git diff --name-only <base> HEAD` in the worktree, returns the changed file paths (empty
  array on error; never throw — audit is best-effort). The worktree was created from
  `origin/main`, so that ref exists.
- After a successful `openPullRequest`, the publish route calls
  `recordAudit({ actorId: session.user.id, action: "publish", paths: await diffPaths(session.worktreePath), prUrl: pr.url })`.
  `recordAudit` is already best-effort (never breaks publish). Match the `AuditEntry` shape and
  the existing call pattern in `src/lib/auth-invite.ts`.

### 7. Login UI (replace the paste-token gate)

- `src/app/(admin)/layout.tsx`: replace `if (!adminEnabled()) notFound()` with
  `if (!adminDeploymentEnabled()) notFound()`. (Surface gate only; the page owns the login UI.)
- `src/app/(admin)/admin/page.tsx`: replace the `needs-token` paste-token form with an
  **email + password** login form. On a 401/403 from `POST /api/admin/session`, set a
  `needs-login` state and render the form. Submit -> `POST /api/auth/sign-in/email` with
  `{ email, password }` (better-auth; same-origin fetch, the `nextCookies` plugin sets the
  httpOnly session cookie automatically). On 200 -> re-run `acquireSession()`. On failure ->
  show the error. Remove the `token`/`tokenError`/`submitToken`/`not-configured` machinery and
  the "ADMIN_TOKEN unset" copy. Add a minimal **logout** button (`POST /api/auth/sign-out`,
  then reset to `needs-login`) so user-switching is possible without clearing cookies by hand
  (closes the "how do I switch user" gap rather than leaving it as debt). Keep the existing
  two-pane shell, the media/attachment flow, the publish button, and all styling otherwise
  unchanged.
- **Delete** `src/app/api/admin/login/route.ts` (the paste-token endpoint is gone).

### 8. Rename `EditScope` values for legibility (the decouple's whole point is the names lied)

`EditScope = "localhost" | "hosted"` now misleads: edit-scope has nothing to do with
localhost-vs-hosted post-decouple. Rename to `EditScope = "full" | "content"`:
- `"localhost"` -> `"full"` (the CONTENT+COMPONENTS+globals allow-set, byte-identical behavior).
- `"hosted"` -> `"content"` (the CONTENT+media+globals narrowed allow-set + the read/list/
  public-media narrowing, byte-identical behavior).
- Update `tools.ts` (the type, `DEFAULT_EDIT_SCOPE` -> `"full"`, `buildAllowGlobs`,
  `allowMatchByScope`, every `scope === "hosted"` check -> `scope === "content"`, the error
  strings) and `tools.editscope.test.mts`.
- **INVARIANT (assert it in the test):** `"content"` scope must produce the EXACT same allow-set
  + narrowing as today's `"hosted"`, and `"full"` the exact same as today's `"localhost"`. This
  is a pure rename; zero behavior change. If you cannot prove equivalence, you over-reached.
- At launch no role maps to `"content"` (everyone is `"full"` per `editScopeForRole`), so the
  narrowing is dormant but available — exactly "EditScope content-only stays a per-role option,
  not the default."

### 9. Dev-auth local-login path (so the operator can prove the gate on localhost)

The seed must produce a superadmin with a KNOWN password (the prod `seed-superadmin.ts` sets a
random throwaway + relies on a Resend reset email, which is not usable for a localhost test).
- Add `scripts/seed-dev-superadmin.ts`: **dev-only** (refuse with a clear error if
  `process.env.NODE_ENV === "production"`). Reads `--email` / `--name` / `--password` args with
  documented dev defaults (e.g. `--email founder@marlinjai.com`); the password must satisfy
  better-auth's `minPasswordLength: 12`. **Idempotent**: if the email already exists, reset its
  password to the given one + ensure `role = "superadmin"` rather than refusing (so re-running is
  a no-op-ish convenience), unlike the bootstrap script which refuses on a non-empty table. Calls
  `auth.api.createUser({ body: { email, name, password, role: "superadmin" } })` for the create
  path. Prints the user id and reminds the operator to set Infisical /dev `SUPER_ADMIN_USER_IDS`.
  Do NOT call `requestPasswordReset` (no email dependency). Source the password preferably from
  an env var (e.g. `DEV_ADMIN_PASSWORD`) with the `--password` arg taking precedence; do NOT hard
  code a committed password literal (GitGuardian) — if you need a fallback for ergonomics, read it
  from env and error out clearly if absent.
- Add a `package.json` script `"db:seed-dev-admin"` wrapping it via `dev-secrets.sh` + the
  tools-loader, exactly like the existing `db:migrate` script (no `tsx`).
- Document in `.env.example` (dev section) the new dev keys: `ADMIN_DEPLOYMENT` (dev `true`) and
  `DEV_ADMIN_PASSWORD`. Do NOT put real values; placeholders only. Do NOT add prod values.

## Tests (the security properties must be asserted DIRECTLY — three prior Workers shipped green-but-broken)

A green self-report has hidden a real bug on every prior 2.5.x chunk because the Worker's tests
encoded its own happy-path mental model. Write the tests that would FAIL on the actual risk:

1. **`auth.gate.test.mts` (rewrite):** with `ADMIN_DEPLOYMENT` unset -> `requireAdminSession`
   returns a 404. With it `"true"` and an injected `getSession` that returns `null` -> 401. With
   a session whose role lacks `content:edit` (e.g. `role: null`, build a fake `AdminSession`) ->
   403. With a valid editor/superadmin session -> returns the session object (not a Response).
   Also assert `adminDeploymentEnabled()` true/false off the env, and `requireRole(fakeSession,
   "content", "edit")` true for editor + superadmin, false for null-role. (Use the injected
   `getSession` seam so NO DB is needed. `requireRole` is pure.)
2. **`tools.editscope.test.mts` (update for the rename):** assert the `"content"` allow-set ===
   the old `"hosted"` set (content+media+globals; rejects `src/app/**`, `src/lib/**`,
   `src/components/**`; the read/list/public-media narrowing fires) and `"full"` === the old
   `"localhost"` set. Equivalence is the point.
3. **`manager.test.mts` (update + add):** (a) with `hostedExecutor: false` the manager NEVER
   reaps (drive an idle TTL past expiry, assert the session survives) — the localhost guarantee;
   (b) with `hostedExecutor: true` an idle session IS reaped after the TTL; (c) **the decouple
   property:** assert that `provision()` spawns the runner with `scrubEnv: true` when
   `hostedExecutor: true` and `scrubEnv: false`/absent when `false`, INDEPENDENT of any
   edit-scope (there is no edit-scope on the manager anymore). Use the injected fake `Runner` and
   capture its `spawn` args.
4. **New pure-helper assertions** (add to an existing fixture or a small new one wired into
   `package.json` `test`): `adminSessionKey(fakeSession)` is deterministic + matches
   `worktreeKeyForUser`; `editorIdentity` falls back to email when name is null;
   `editScopeForRole("superadmin") === "full"`, `editScopeForRole("editor") === "full"`,
   `editScopeForRole(null) === "content"`.
5. All existing tests (`tools.fence.test.mts`, `runner.test.mts`, `media.test.mts`, the
   deck-core tests) MUST stay green. `pnpm lint` (eslint --max-warnings=0) + `pnpm exec tsc
   --noEmit` clean. Wire any new fixture into the `package.json` `test` script.

## Definition of done

- The stopgap paste-token gate is gone; `/admin` + `/api/admin/*` are gated by
  `ADMIN_DEPLOYMENT` (surface) + a valid better-auth session carrying `content:edit`.
- Secret-starve + idle-reaping key off `isHostedExecutor()` (deployment), NOT edit-scope;
  edit-scope keys off the user's role (default full); the two are independently testable.
- Commits attribute to the editor's identity; every publish writes a `recordAudit` row.
- Per-admin/per-session worktree key (`worktreeKeyForUser`) wired into all four routes,
  identically derived via `adminSessionKey`.
- A dev-only known-password seed + `db:seed-dev-admin` + `.env.example` dev docs exist, so the
  gate is loginable on localhost.
- `EditScope` renamed to `"full" | "content"` with proven behavior-equivalence.
- Full `pnpm test` + lint + tsc green. Merging is public-site-safe (prod `ADMIN_DEPLOYMENT`
  unset -> `/admin` 404; public pages unchanged) — state this in your summary.

## Constraints

- Stay in this worktree. Do not modify files outside it. Do not push to any remote, open a PR,
  merge, or deploy. The operator does all of that after an adversarial review + the live boot.
- Do NOT touch `infra/**`, `.github/**`, `Dockerfile`, `deploy.yml`, Terraform, or Infisical
  config. Do NOT set `ADMIN_DEPLOYMENT=true` in any committed file (HARD GATE).
- Do NOT build 2.5.2 or 2.5.4. Do NOT run a real `next dev` boot or a real DB seed (no DB in
  your env) — that live test is the operator's job; your job is build-to-green with the
  injected-seam unit tests above.
- Single commit on this branch with a conventional-commit message describing the WHY. File any
  pre-existing issue you notice as an `open_thread` in your final summary rather than fixing it
  out of scope.
- When done, output a final summary: what changed, which tests assert which security property,
  and an explicit confirmation that the HARD GATE holds (no `ADMIN_DEPLOYMENT=true` committed,
  merge is public-site-safe).
