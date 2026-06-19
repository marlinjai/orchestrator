---
task: storage-brain-auth-brain-dashboard-session
spec: docs/plans/2026-06-16-storage-brain-auth-brain-dashboard-session.md
shared_state: [migrations, lockfile]
verify: pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal

Implement the leaf spec at `docs/plans/2026-06-16-storage-brain-auth-brain-dashboard-session.md`:
make the Storage Brain dashboard authenticate humans via auth-brain's `lumitra_session`
(`verifySession` + `can(user, 'platform.admin', platform)`), with the existing admin-key
iron-session kept as a transitional FALLBACK (hybrid, fail-closed). Move the dashboard's backend
API credential to a server-side env var for the auth-brain path. Add the nullable
`auth_workspace_id` binding on the `tenants` table as plumbing. This is slice 2A; it unblocks
the upload UI (slice 3).

## Read first

- The spec in full (auth model, hybrid fallback, env credential rationale, auth_workspace_id
  plumbing, file list, tests, out-of-scope).
- The pattern to mirror: `analytics-platform/.../src/lib/auth-brain.ts` (auth-brain client
  singleton) and its `middleware.ts` (session-cookie redirect).
- Existing storage-brain auth to extend, not break:
  - `packages/dashboard/src/lib/session.ts` (iron-session, cookie `sb-dashboard`)
  - `packages/dashboard/src/lib/sdk.ts` (`getAdmin()`), `.../middleware.ts`, `.../app/api/auth/*`
  - `packages/api/src/adapters/database/d1.ts` (tenant mapping/create/update) and
    `packages/api/migrations/` (next number is 0005)
  - `packages/shared/src/types.ts`, `.../database-adapter.ts`
- Test conventions: `packages/*/src/**/*.spec.ts` (vitest, mock the DB with `vi.fn()`, build the
  app with `createApp(...)` and use `app.request(...)`). No Docker/testcontainers in this repo.

## Definition of done

Everything in the spec body, plus the standing gates:

- `pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test` all pass.
- Hybrid auth tests exist and pass: auth-brain session + `can(platform.admin)=true` → allowed;
  valid session + `can=false` → UNAUTHORIZED (not silently allowed); legacy iron-session →
  allowed; neither → redirect/`null`; a thrown/timed-out `verifySession`/`can()` → unauthorized
  (fail-closed), never an allow.
- `auth_workspace_id` round-trips through migration 0005 + d1 create/map/update, and existing
  tenants with NULL `auth_workspace_id` still map with no regression to existing d1 tests.
- The legacy admin-key login and the `api_key_hash` tenant path remain fully working.
- Spec frontmatter `status: draft` → `status: done`.
- Any STATUS/ROADMAP index row updated using the existing column format exactly.
- Single commit, conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not push to any remote.
- Additive / non-breaking: do NOT remove the admin-key login, the iron-session, or
  `getTenantByApiKey`. Do NOT add service-account-key (`verifyApiKey`) auth to the Cloudflare
  Worker API — that is a deferred slice and explicitly out of scope.
- Secrets: `STORAGE_BRAIN_ADMIN_KEY` and `SESSION_SECRET` are server-only env vars. Never expose
  them to the client bundle, never log them, never commit a real value (only `.env.example`
  placeholders). The hardcoded 32-char session secret fallback must be gated to dev-only
  (NODE_ENV check), not shipped as a prod default.
- Use the auth-brain SDK's published version (`@marlinjai/auth-brain-sdk`, the 1.0.x on npm).
  This slice only needs `verifySession` + `can()`; it does NOT need `verifyApiKey`.
- No em-dashes or en-dashes in any code, comment, or doc you write.
- Do NOT do slice 3 (upload UI), per-tenant `can()` filtering, or workstream 4.

## Pre-existing typecheck debt — fix it as part of this slice

`pnpm run typecheck` (`tsc --noEmit`) is RED on `main` already, independent of your changes:
~100 `error TS18046: 'body' is of type 'unknown'` across existing spec files (`packages/api/src/app.spec.ts`,
`routes/*.spec.ts`, `services/webhook.spec.ts`, etc.), because `const body = await res.json()`
returns `unknown` and the tests then access `body.field`. The repo's CI only runs `vitest run`,
so this was never caught. Your verify gate includes `typecheck`, so you MUST make it green
repo-wide. This is in scope (per the no-tech-debt rule): fix the latent debt, do not work around it.

- Fix mechanically and correctly: give each `res.json()` (and any similar `unknown`) a proper
  type. Prefer a real response type/interface where one exists; a narrow cast
  (`as { error?: string; ... }` / `as Record<string, unknown>`) is acceptable in tests. Do NOT
  blanket-`any` and do NOT disable the check or edit tsconfig to exclude specs.
- Also fix the two `webhook.spec.ts` errors (TS2488 iterator / TS2532 possibly-undefined).
- After your fix, `pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test` must ALL
  be green. A second commit for the typecheck cleanup (separate from the feature commit) is fine;
  they squash on merge.

## Notes

- The dashboard is Next.js 15 App Router on Node, not Workers, so the SDK's fetch-based client
  is fine there. The API worker is unchanged in this slice.
- If you discover genuinely out-of-scope work, file it as an `open_thread`, not a bare TODO.
