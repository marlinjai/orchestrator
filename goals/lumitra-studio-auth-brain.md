---
task: lumitra-studio-auth-brain
spec: docs/specs/2026-06-01-auth-brain-v1.md
shared_state: [prisma, migrations, lockfile, next-config, claude-md]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

Implement **Auth Brain v1** for Lumitra Studio per the spec at `docs/specs/2026-06-01-auth-brain-v1.md`: add real per-user login (Auth.js / NextAuth v5, Google OAuth, JWT sessions, email allowlist) so approved humans can use the hosted web UI, while the existing `SERVICE_TOKEN` bearer path keeps working unchanged for the CLI and server-to-server callers. The acceptance bar: a logged-out browser is redirected to `/login`; an allowlisted Google account signs in and `/api/*` calls succeed from the browser; a `SERVICE_TOKEN` caller still works; non-allowlisted accounts are refused.

## Read first

- The spec in full: `docs/specs/2026-06-01-auth-brain-v1.md` (Decision, Scope, Files and changes, Acceptance, Design decisions).
- `src/middleware.ts` (the current service-token gate you are extending: keep the constant-time compare, the misconfigured-500, the no-token-logging guarantees, and `runtime = 'nodejs'`).
- `prisma/schema.prisma` (note: `model Session` is CHAT sessions; do NOT collide with it. JWT strategy means you add NO auth Session table).
- How the UI calls the API: `src/app/page.tsx`, `src/components/BrandPanel.tsx` (bare same-origin `fetch('/api/...')`; once a session cookie exists these succeed with no Authorization header).
- `package.json` (Next 16.2, React 19.2, Prisma 7 with `@prisma/adapter-pg`), the repo `CLAUDE.md`, and existing test patterns under `src/**/__tests__` / `*.spec.ts` (vitest).

## Definition of done

1. `next-auth@^5` (Auth.js) added; config in `src/auth.ts` (or `src/lib/auth/config.ts`): Google provider, JWT session strategy, `trustHost`, and a `signIn` callback that rejects any email not in `AUTH_ALLOWED_EMAILS` (comma-separated). Config resolves env LAZILY: do NOT throw at module load when `AUTH_*` is absent (mirror `src/middleware.ts`), so `next build` / `next dev` do not crash without secrets.
2. `src/app/api/auth/[...nextauth]/route.ts` wired.
3. `src/lib/auth/verifyRequest.ts`: a single seam returning `{ kind: 'user', email } | { kind: 'service' } | { kind: 'none' }`. This is the unit a future shared Auth Brain absorbs; keep it clean and isolated.
4. `src/middleware.ts` extended to a DUAL gate on `/api/*`: authorize if EITHER a valid Auth.js session for an allowlisted user OR a valid `SERVICE_TOKEN` bearer. Exempt `/api/health` AND `/api/auth/*`. Preserve every existing service-token guarantee.
5. `/login` page with "Sign in with Google"; a sign-out control in the app shell; unauthenticated app navigation redirects to `/login`. Do not add Authorization headers to the existing UI fetches (the cookie carries the session).
6. Tests (vitest): allowlisted signs in; non-allowlisted rejected; `/api/*` passes with a session cookie; passes with the service token; 401 with neither; `/api/health` and `/api/auth/*` public. Mock the session; never call Google.
7. `docs/internal/auth.md`: the login flow, the allowlist env var, and confirmation the CLI/service-token path is unchanged.
8. Verify with the DB-free auth and middleware tests: `pnpm exec vitest run --config vitest.middleware.config.ts` plus any new `src/lib/auth/**` specs you add, and `pnpm lint` and typecheck. Do NOT run the full `pnpm test` integration suite and do NOT try to start a database: on this machine the local test DB (localhost:5432) is occupied by another project, so the integration suite cannot connect. The operator runs the full suite at merge. A bare `pnpm build` failing only on absent `DATABASE_URL`/`AUTH_*` is the known `infisical run -- pnpm build` pattern, not a regression.
9. Spec frontmatter `status` stays `decided` (do not flip to done; the human verifies in prod).
10. Single commit on this branch, conventional message describing the WHY (humans cannot use the token-gated UI; add login without breaking the machine path).

## Constraints (hard, do not violate)

- **Do NOT run any database migration against a non-local database. Do NOT deploy. Do NOT write or read production secrets. Do NOT create the Google OAuth client.** Those are Marlin's steps (irreversible_ops). If your change needs a schema migration (v1 should need NONE, since JWT sessions add no table), generate it with `prisma migrate dev --create-only` against a LOCAL throwaway DB only, commit the migration file, and STOP. Never apply to prod.
- Stay in this worktree. Do NOT modify files outside it. Do NOT push to any remote (the operator handles push/PR/merge).
- Do NOT log the service token or any session token, even partially, on any path.
- Do NOT remove or weaken the existing `SERVICE_TOKEN` behavior. It must keep working identically.
- No em-dashes or en-dashes in any output, code comment, or commit message (repo style rule).
- Report progress via the `update_state` MCP tool: `file_touched` as you create files, `decision` for any non-obvious call (e.g. how the dual gate resolves precedence), `open_thread` for anything deferred (e.g. the `User`-table self-serve path), `commit` when you commit.
- If a genuine fork has no clear answer from the spec, make the call that keeps the verification logic easiest to later extract into a shared service, record it as a `decision`, and continue. Do not stall.

## Notes

- JWT session strategy is deliberate: it avoids a second `Session` table (the chat `Session` model already exists) and any `@auth/prisma-adapter` + Prisma 7 driver-adapter risk. If you believe a database adapter is unavoidable, that is a `scope_change`: escalate rather than introduce a colliding `Session` table.
- Local test DB: `localhost:5432` is held by another project's Postgres on this machine, so the integration suite's database is unavailable in this run. Validate via the DB-free middleware/auth tests only. Do NOT run `docker compose up` or the full `pnpm test`. Do not burn iterations trying to start a database; if you believe DB-bound verification is essential to this change, escalate instead.
- Out of scope (do NOT build): a separate deployed Auth Brain service, roles/permissions beyond the allowlist, database User records / self-serve signup, email magic-link. Note them as `open_thread` if relevant.
