---
task: arbosano-phase-4-identity
spec: plans/2026-05-30-phase-4-identity-better-auth.md
marlin_proxy: shadow
shared_state: [lockfile, env]
---

# Goal

Implement arbosano content-as-code **Phase 4**: better-auth (email + password + reset, super-admin-provisioned, two roles named after the auto-merge zones) backed by an operational Postgres, plus the deploy-time CI migration and the primitives Phase 2 / Phase 2.5 / Phase 5 consume (`getAdminSession`, `requireRole`, `worktreeKeyForUser`, `recordAudit`). You run inside a git worktree on branch `feat/phase-4-identity` off `main`. Build it to green and **verify the migration + auth against a LOCAL THROWAWAY DOCKER POSTGRES you spin up and tear down yourself** (Docker is available). Do NOT push, do NOT open a PR, do NOT merge, do NOT deploy. The operator reviews, runs the live-integration verification, and opens the PR.

The authoritative spec is `plans/2026-05-30-phase-4-identity-better-auth.md`. **Read it fully (all sub-phases 4.0 to 4.6, Key components, Reuse, Risks) before writing any code.** The cross-phase contracts are in `plans/2026-05-30-content-as-code-roadmap-phases-2-5.md` ("Cross-phase contracts"); read that section too.

## Repo-state precondition

- You are on branch `feat/phase-4-identity` in a worktree off `main`. `main` HEAD is `1fdbded` (the content-as-code cascade Phases 2 + 3 AND the ads/SEO pitch work are all merged; the handover docs that say HEAD is `fc7d0ed` are stale on that one point only).
- Working tree must be clean at start. If not, escalate.
- These already exist on `main` and you MUST reuse, never recreate:
  - `src/lib/zones.ts`: `CONTENT_GLOBS`, `COMPONENTS_GLOBS`, `BLOCKED_GLOBS`, `Zone`, `ZONE_POLICY`. Phase 4 `auth-roles.ts` IMPORTS these; it does NOT edit `zones.ts`.
  - `src/app/api/contact/route.ts`: the exact Resend wiring (`RESEND_API_KEY` + `CONTACT_FROM_EMAIL`, the creds-missing -> 503 pattern) that `auth-email.ts` mirrors.
  - `src/lib/storage-brain.ts`: the `globalThis`-guarded-factory pattern the `pg` Pool singleton mirrors (no HMR Pool leak).
  - `src/app/api/health/route.ts`: stays DB-free and UNCHANGED (a degraded DB must never flap the container).
  - `entrypoint.sh` + `Dockerfile`: UNCHANGED. The entrypoint already does `infisical run --path / --env prod`, so every new `/prod` secret reaches the app with zero entrypoint/Dockerfile change. The migration is in CI precisely because the runtime image has no `src/`/tsconfig/git.
  - `deploy.yml` (`.github/workflows/deploy.yml`): the build -> deploy chain the new `migrate` job slots into.

## Decisions already taken (do NOT re-litigate; list them in your final report)

- **CI-Postgres reachability path = Coolify one-off command on the Hetzner host (DB stays private).** This is an infra-coupled trigger (needs the Coolify app uuid + `COOLIFY_TOKEN`, which are Marlin's). So: WRITE `scripts/migrate.ts` and a `deploy.yml` `migrate` job in a clean, parameterized form (`infisical run --token <INFISICAL_MI_TOKEN> ... -- pnpm exec tsx scripts/migrate.ts`, positioned so the order is build -> migrate -> deploy-verify webhook). File an `open_thread` that the operator finalizes the exact host-one-off Coolify-API invocation after Marlin provides the app uuid + confirms the path. Do NOT invent a public-port + IP-lock (that is the rejected fallback).
- **Local verification DB = a throwaway Docker Postgres you run yourself** (`postgres:17-alpine`, host port 5433 to avoid colliding with 5432), `DATABASE_URL` set in your shell env for the verify only, torn down (`docker rm -f`) when done. NEVER point at prod, NEVER read Infisical, NEVER write a `.env` file.
- **Roles mapped to zones** (`auth-roles.ts`): `createAccessControl` with resources `content`, `components`, `infra`. `editor = {content: ["edit","publish"]}`; `superadmin` = all three resources, but **NO role ever gets `infra:publish`, only `infra:approve`** (infra is structurally never auto-mergeable; this mirrors `BLOCKED_GLOBS`).
- **Open signup OFF** (`disableSignUp: true`), argon2id custom hash/verify, `minPasswordLength: 12`, single-use 30-min reset (`resetPasswordTokenExpiresIn: 1800`, `revokeSessionsOnPasswordReset: true`), DB-backed rate limits (sign-in 5/60s, request-reset 3/60s, reset 5/60s), secure httpOnly cookies, uuid ids, admin plugin with `defaultRole: "editor"`, `adminRoles: ["superadmin"]`, `adminUserIds` from `SUPER_ADMIN_USER_IDS.split(",")`, impersonate endpoints disabled.
- Auth email copy is **German with NO dashes** (parens for asides, e.g. "(Link 30 Min gueltig)").

## Build (sub-phase order from the spec; 4.0 is NOT yours)

- **4.0 (terraform: NOT yours).** The 512M Postgres cap + the CI-reachability terraform live in the SEPARATE `infra` repo (`~/software-dev/infra/deployments/arbosano`), OUTSIDE this worktree. Do NOT touch it. It is Marlin's by-hand `terraform apply`. File it as an `open_thread`.
- **4.1 deps + onlyBuiltDependencies.** Add runtime `better-auth`, `pg`, `@node-rs/argon2`; dev `@better-auth/cli`, `@types/pg`, `tsx`. Add `pg` + `@node-rs/argon2` to `pnpm.onlyBuiltDependencies` (native builds; `@node-rs/argon2` ships a prebuilt `linux-arm64-musl` so it works in the alpine ARM image). This is the one in-scope `package.json` + `pnpm-lock.yaml` edit. Do NOT write Infisical secrets (Marlin does that): instead file an `open_thread` listing the exact `/prod` AND `/dev` secret names to create: `DATABASE_URL`, `BETTER_AUTH_SECRET` (distinct per env), `BETTER_AUTH_URL` (`https://arbosano.lumitra.co` prod, `http://localhost:3000` dev), `SUPER_ADMIN_USER_IDS` (set after the seed). Note `RESEND_API_KEY` + `CONTACT_FROM_EMAIL` already exist and are reused.
- **4.2 the better-auth instance.** `src/lib/auth.ts` (single source of truth; the CLI, the route, and `getMigrations` all read `auth.options`), `auth-password.ts` (argon2id: memoryCost 65536, timeCost 3, parallelism 4), `auth-roles.ts` (the zone resources above), `auth-email.ts` (Resend reuse, German, dash-free). `pg` Pool behind a `globalThis` singleton.
- **4.3 HTTP surface + session gate primitive.** `src/app/api/auth/[...all]/route.ts = toNextJsHandler(auth)`. `src/lib/auth-session.ts` exports `getAdminSession(headers)` + `requireRole(session, zone, action)`. Do NOT build the `/admin` UI (that is Phase 2 / Phase 2.5). `/api/health` stays DB-free.
- **4.4 deploy-time migration.** `scripts/migrate.ts` = `getMigrations(auth.options).runMigrations()` (idempotent) then run `scripts/sql/operational.sql` (the `audit_log` table: `id uuid PK, actor_id uuid FK -> "user"(id), action text, paths text[], pr_url text, reviewer_verdict text, created_at timestamptz`). Edit `deploy.yml` to add the `migrate` job per the decision above (build -> migrate -> deploy-verify).
- **4.5 invite flow + deactivation.** `src/lib/auth-invite.ts`: server-only `createUser({role:"editor", password:<random>})` then `requestPasswordReset(...)` emailing the single-use token; writes an `audit_log` row. Deactivation = `banUser` + `revokeUserSessions` + an audit row. Impersonate disabled (documented, not a TODO).
- **4.6 seed + the identity contracts.** `scripts/seed-superadmin.ts` (`createUser({role:"superadmin"})`, refuses if any user exists). In `auth-session.ts`: a pure `worktreeKeyForUser(user)` returning `staging/<slug(email)>/<sessionId>`, and the typed `recordAudit(...)` writer Phase 5 calls.

## Definition of done

- `pnpm exec eslint --max-warnings=0 .` passes.
- `pnpm exec tsc --noEmit` passes.
- `pnpm build` passes with a dummy env (the build needs no real secret: health is DB-free).
- `pnpm exec @better-auth/cli generate` emits the user/session/account/verification/rateLimit schema.
- **Against the throwaway Docker Postgres**: `pnpm exec tsx scripts/migrate.ts` creates the better-auth tables + the `audit_log` table, and is a CLEAN NO-OP on a second run (idempotency proven). Tear the container down after.
- `seed-superadmin.ts` creates exactly one superadmin against a fresh DB and REFUSES on re-run; the created account's `account.password` starts `$argon2id$` (prove argon2id, not the default scrypt).
- `grep -rnP '[\x{2013}\x{2014}]' src/lib/auth-email.ts` (and all new files) finds nothing.
- `update_state(kind="commit")` after each commit; `kind="file_touched"` per new file; `kind="decision"` per non-obvious choice; `kind="open_thread")` for: (1) Marlin's terraform apply (512M cap + the host-one-off reachability), (2) the exact Infisical `/prod` + `/dev` secret names to create, (3) the `INFISICAL_MI_TOKEN` GH secret for the migrate job, (4) the operator finalizing the host-one-off Coolify-API migrate trigger, (5) running the prod seed once + writing its id into `/prod SUPER_ADMIN_USER_IDS`.
- Conventional-commit messages (dash-free), one commit per sub-phase is fine.
- Final message: decisions taken, files added, deps added, open threads, and confirmation that lint + tsc + build + the local-Docker-PG migration + idempotent re-run + the `$argon2id$` check are all green.

## Constraints

- Stay inside this worktree. Do not modify any file outside it. In particular do NOT touch the separate `infra` repo (terraform) and do NOT write any Infisical secret: those are Marlin's by-hand steps, filed as open_threads.
- Do NOT push, open a PR, merge, or deploy.
- No em-dashes (U+2014) or en-dashes (U+2013) anywhere: code, comments, strings, commit messages, SQL, the German email copy. Use colons, parens, commas, periods.
- Secrets come from `process.env` (Infisical at runtime) only: never hardcode, never expose to the browser bundle, never write `.env`.
- `entrypoint.sh`, `Dockerfile`, `api/health/route.ts` stay UNCHANGED. `zones.ts` is IMPORTED, not edited.
- Expected footprint: ~10 to 12 new files + the deploy.yml migrate job + the declared deps. Material scope beyond that is an escalation.

## Escalation rules

- Working tree not clean at start: escalate.
- The argon2id ARM binary will not load even after adding to `onlyBuiltDependencies`: bcrypt is the HARD-RULE-allowed fallback; note it and continue, do not silently ship scrypt.
- The installed `better-auth` version's `getMigrations` / admin-plugin / access-control API shape is ambiguous and you would have to guess: escalate rather than guess (auth is security-critical and human-gated forever).
- Docker is unavailable for the local verify: build to green anyway, mark the DB verification as an open_thread for the operator, and escalate the missing verification (do NOT claim the migration is verified if you could not run it).
- Scope creep beyond the footprint above, or any need to touch a `BLOCKED_GLOBS` file other than `package.json`/`pnpm-lock.yaml`/`deploy.yml`: escalate.

## Out of scope (stated, not parked)

- The terraform apply (512M cap + CI reachability), all Infisical secret writes, the `INFISICAL_MI_TOKEN` GH secret, the prod seed run: Marlin's by-hand steps (open_threads).
- The exact host-one-off Coolify-API migrate trigger finalization: operator step (open_thread).
- The `/admin` UI and its auth-gate swap from the stopgap `adminEnabled()` to better-auth: that is Phase 2.5.
- Phase 5 (reviewer, MERGE_TOKEN, auto-merge).
- Any push, PR, merge, or deploy.
