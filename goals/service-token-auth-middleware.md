---
task: service-token-auth-middleware
spec: docs/specs/2026-05-25-service-token-auth-middleware.md
---

# Goal

Implement slice 2 of the Lumitra Studio internal-infra deploy v0.1: gate the Next.js HTTP API behind a single shared bearer token in `process.env.LUMITRA_STUDIO_SERVICE_TOKEN`, and add an unauthenticated `/api/health` route for Coolify liveness checks. Single conventional commit on the existing `feat/service-token-auth-middleware` branch in this worktree.

## Read first

- The spec at `docs/specs/2026-05-25-service-token-auth-middleware.md` (full contents: Goal, Why this shape, Scope, Acceptance criteria, Non-acceptance, Risks)
- The sibling spec `docs/specs/2026-05-25-coolify-deploy.md` for context on the healthcheck consumer (do not implement it)
- `src/app/api/` directory (every existing route) to confirm none of them rely on global middleware behavior already
- `src/lib/jobs/queue.ts` to find the pg-boss queue-size probe API for the health route
- `prisma/schema.prisma` and any client wrapper (e.g. `src/lib/db.ts`) for the DB ping
- `next.config.ts`, `package.json`
- `CLAUDE.md` if present

## Definition of done

Per the spec's Acceptance criteria, verified locally:

- `src/middleware.ts` exists with:
  - `export const runtime = 'nodejs'` (required for `crypto.timingSafeEqual`)
  - `export const config = { matcher: ['/api/:path*'] }`
  - Inside the handler, an early `return NextResponse.next()` for `/api/health` BEFORE the bearer check (matcher-level negative lookahead avoided as brittle across Next versions)
  - Bearer token parsed from `Authorization: Bearer <token>` header
  - Token comparison uses `crypto.timingSafeEqual` over equal-length Buffers; length mismatch first short-circuits with a dummy compare against a same-length zero buffer to keep timing roughly constant
  - Token env value `process.env.LUMITRA_STUDIO_SERVICE_TOKEN` is read once and `.trim()`-ed at first request, cached at module level
  - If the env var is unset OR shorter than 32 chars at request time, return 500 `{error: 'service_token_misconfigured'}`. Do NOT throw at module load (would crash `next dev` / `next build` locally when the var is absent).
  - On miss: `NextResponse.json({ error: 'unauthorized' }, { status: 401 })`
  - On match: `NextResponse.next()`
  - No Prisma import, no DB read, no logging of the token (not even partial)
  - Catch-all error handler returns generic 401 without exposing error messages
- `src/app/api/health/route.ts` exists with:
  - `GET` handler returning `{ status: 'ok', db: 'ok'|'degraded'|'down', queue: 'ok'|'degraded'|'down', version: string }` always with HTTP 200
  - `db`: Promise.race between `prisma.$queryRaw\`SELECT 1\`` and a 1500ms timeout. Errors / timeouts return `'down'`. Errors caught and not propagated.
  - `queue`: cheap pg-boss probe (queue size, status, or equivalent; verify against `src/lib/jobs/queue.ts`). Errors return `'down'`.
  - `version`: `process.env.LUMITRA_STUDIO_COMMIT_SHA` if set, else `package.json` version (`'0.1.0'`)
  - No auth, no tenant context, no caller logging
- `src/middleware.spec.ts` (or `.test.ts` per project convention) covering:
  - Missing `Authorization` header: 401
  - Wrong scheme (`Basic <token>`): 401
  - Correct scheme, wrong token: 401 (constant-time path exercised)
  - Correct token: pass-through (mock downstream)
  - `/api/health` skipped regardless of header
  - Env var unset at request time: 500 with `service_token_misconfigured`
  - Env var present but shorter than 32 chars: 500 with `service_token_misconfigured`
- README.md (root) gets an `## Auth` section documenting the bearer pattern and the rotation procedure (update Infisical secret, redeploy, propagate to consumer apps). Place it logically alongside any existing setup section; do not invent a new top-level heading hierarchy.
- Spec file `docs/specs/2026-05-25-service-token-auth-middleware.md`: frontmatter `status: draft` becomes `status: in-progress` at start, then `status: completed` at end (per `document-lifecycle` standard).
- Single conventional commit: `feat(api): service token middleware + health route`. Body summarizes the matcher, the constant-time compare, and the health-route contract.
- `pnpm exec tsc --noEmit` clean.
- `pnpm --filter @marlinjai/lumitra-core test` still passes (no regression in lib package, even though this slice does not touch it).
- The middleware unit tests pass (`pnpm test src/middleware`).
- Running `pnpm dev` locally (do NOT actually start the server in the orchestrator run; just confirm the code typechecks and the test suite passes; the operator runs `pnpm dev` post-merge if smoke is needed).

## Constraints

- **Stay in this worktree.** Path is `/Users/marlinjai/software-dev/ERP-suite/projects/lumitra-studio-orch-service-token-auth-middleware`. Do not modify files anywhere else.
- **Do not push to any remote.** Branch stays local; the operator pushes after gate.
- **Do not touch the database** (no migrate, no docker-compose, no schema edits). Prisma client read paths in the health route are fine.
- **Do not introduce ApiKey table, rate limiting, CORS config, request logging, mTLS, IP allowlists.** Explicitly out of scope per the spec.
- **Naming**: use `LUMITRA_STUDIO_SERVICE_TOKEN` and `LUMITRA_STUDIO_COMMIT_SHA`. Never bare `LUMITRA_*`.
- **Typography**: no em-dash `—` or en-dash `–` anywhere (commit message, code comments, spec status update, README). Use colons, parentheses, commas, periods.
- **No `--no-verify`**, no force operations.
- **Conventional commit only**, single commit, no WIP commits, no follow-up cleanup commits.

## Escalation triggers

Stop and escalate (via `update_state` with `kind="escalation"`) if:

- `crypto.timingSafeEqual` is unavailable in the Next 16.2.1 middleware runtime (the spec assumes `runtime = 'nodejs'`; if Next has changed this, surface the constraint)
- pg-boss does not expose a cheap, non-blocking queue-size or status method (check `src/lib/jobs/queue.ts` for what's there)
- Adding `runtime = 'nodejs'` to the middleware breaks any existing API route that depended on Edge-runtime middleware (unlikely; this app has no such dependency, but verify)
- You find yourself wanting to add an ApiKey table, rate limiting, CORS, or any of the explicitly-out-of-scope items: stop
- Health route would need to import Prisma but Prisma client construction at module load throws (in which case lazy-instantiate inside the GET handler)

## Notes

- Worktree base branch: `main` (slice 1 landed in PR #5). The worktree branch is `feat/service-token-auth-middleware` already created off `main`.
- The `runtime = 'nodejs'` declaration is required because Next.js Middleware defaults to Edge, which doesn't have Node `crypto.timingSafeEqual`. Confirmed supported as of Next 13.x and remains so in Next 16.
- The token is generated by Marlin via `openssl rand -base64 48` and stored in Infisical pre-slice-3. For local dev / tests, mock the env or use `.env.local` (not committed). Tests should use `vi.stubEnv` or equivalent.
- Re: the open thread from slice 1 about app-side `pnpm test` needing a DB (vitest globalSetup): does NOT block this slice's tests. The middleware tests should not require DB; if globalSetup interferes, exclude the middleware test from the global-setup pipeline (use a separate vitest config or `--no-setup` if supported). Escalate if you cannot work around it.
- Final message at the end of the run: confirm the branch name, the commit SHA, the routes touched (`src/middleware.ts`, `src/app/api/health/route.ts`, `src/middleware.spec.ts`, `README.md`, the spec file), and any `open_thread` entries.
