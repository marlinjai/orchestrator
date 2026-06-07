---
task: lumitra-auth-phase-0
spec: ~/software-dev/knowledge-base/research/2026-06-07-auth-centralization-scoping.md
shared_state: [auth]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
verify: pnpm exec vitest run --config vitest.middleware.config.ts && pnpm exec tsc --noEmit && pnpm exec eslint src/lib/auth src/middleware.ts
verify_fix_cap: 2
verify_timeout_s: 600
---

# Auth Phase 0: the Lola safety net (fail-closed test + SERVICE_TOKEN_NEXT rotation + env reconciliation)

Context: the studio gates `/api/*` with a dual gate (NextAuth session OR `SERVICE_TOKEN` bearer) in `src/middleware.ts` + `src/lib/auth/*`. Lola Stories is the critical machine caller: its backend POSTs to `/api/generate` with `Authorization: Bearer SERVICE_TOKEN` and MUST never break. This slice is Phase 0 of the auth-centralization plan (see the spec doc): the safety net, done before any AuthBrain wiring. Read the relevant parts of the spec doc first.

This is AUTH-SENSITIVE. Do NOT change the existing dual-gate behavior: the bearer branch must stay orthogonal to the session branch, keep the constant-time token compare, the `service-misconfigured` 500, the no-token-logging guarantee, and `runtime = 'nodejs'`. You are ADDING a safety net, not refactoring the gate.

## 1. Fail-closed contract test (the core deliverable)

The fail-open risk: `/api/generate` and `/api/v1/jobs/[jobId]` have ZERO in-handler auth (the middleware is the sole gate), and the existing tests call `middleware()` in-process, BYPASSING the Next matcher, so a matcher regression that drops a route fails OPEN and is not caught. Add a test (extend `src/middleware.spec.ts` or a new spec under `src/lib/auth/__tests__/`) that closes this, runnable under `vitest.middleware.config.ts` (DB-free):
- Assert the exported `config.matcher` in `src/middleware.ts` actually MATCHES `/api/generate` and `/api/v1/jobs/<id>` (build the path-matching check from the matcher pattern, so narrowing the matcher fails this test).
- Assert the fail-CLOSED negative: `middleware()` on `/api/generate` and on `/api/v1/jobs/<id>` with NO credentials (no bearer, no session) returns 401 (never a silent pass-through).
- Assert a valid `SERVICE_TOKEN` bearer to `/api/generate` returns next() (200-path), with `getToken` mocked to null (the existing harness pattern).
Note in a comment that a full over-HTTP test (booting the Next server) is the stronger future form; this matcher-config + in-process negative is the DB-free guard for now.

## 2. SERVICE_TOKEN_NEXT dual-accept rotation

Today `getServiceToken()` (`src/lib/auth/verifyRequest.ts:54-60`) reads exactly one env var, so rotating the token is a hard cutover with a Lola-401 window. Add dual-accept:
- `getServiceToken()` (or the compare site) accepts a bearer that matches EITHER `process.env.SERVICE_TOKEN` OR `process.env.SERVICE_TOKEN_NEXT` (both trimmed, both length-checked >= the existing minimum). Keep the constant-time compare for each; a match against either yields `{kind:'service'}`. If only one is configured, behave exactly as today.
- Preserve the module-level caching pattern (cache both, resolve once).
- Tests (under the middleware config): bearer == SERVICE_TOKEN passes; bearer == SERVICE_TOKEN_NEXT passes; bearer == neither fails (bad-bearer); neither configured + bearer presented yields service-misconfigured (unchanged).

## 3. Env reconciliation (docs)

- Fix the stale spec `docs/specs/2026-05-25-service-token-auth-middleware.md`: it names the studio-side var wrong. The studio reads `SERVICE_TOKEN` (verifyRequest.ts:56); Lola holds the SAME value under its own env var `LUMITRA_STUDIO_SERVICE_TOKEN`. Correct the spec to state both names and that they hold the same secret.
- Add a short rotation runbook (a new `docs/internal/service-token-rotation.md`): the invariant (studio `SERVICE_TOKEN` == Lola `LUMITRA_STUDIO_SERVICE_TOKEN`, same value, two Infisical projects), and the zero-downtime procedure using the dual-accept window (set `SERVICE_TOKEN_NEXT` in both projects, deploy, verify via logs + the contract test, promote NEXT to primary, retire the old). Do NOT put any real secret value in the doc.

## Acceptance (definition of done)

1. The fail-closed test (matcher coverage + no-credential 401 on both gated routes + valid-bearer pass) is green under `vitest.middleware.config.ts`.
2. SERVICE_TOKEN_NEXT dual-accept works and is tested; single-token behavior is byte-for-byte unchanged.
3. The stale spec is corrected and the rotation runbook exists.
4. The verify command passes: `vitest --config vitest.middleware.config.ts` + `tsc --noEmit` + `eslint src/lib/auth src/middleware.ts`.

## Hard constraints

- Touch ONLY auth: `src/middleware.ts`, `src/lib/auth/*`, the two docs. Do NOT touch any route handler, the providers/jobs, the prisma schema, the `packages/` (the scene-core slice is a separate parallel task: do not go near `packages/studio-scene-core` or `packages/lumitra-core`).
- Do NOT change the dual-gate semantics; the session branch and the bearer branch stay independent. Lola's path stays byte-for-byte working.
- Do NOT deploy, publish, rotate real secrets, or run `infisical`/secret commands. The verify tests are DB-free under the middleware config.
- Conventional commits, body lines <= 100, no em-dashes or en-dashes. Single branch; never push to main; never `gh pr merge` (operator merges).
