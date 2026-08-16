---
task: sp-tenancy-gate
spec: docs/plans/2026-08-16-multi-tenancy.md
shared_state: [lockfile, env, next-config]
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Implement **slice S2** of `docs/plans/2026-08-16-multi-tenancy.md`: gate
social-planner on the per-company `social` app grant using
`@marlinjai/auth-brain-nextjs` 0.4.1 in appGrant mode.

Right now the app only calls `verifySession`. Because `lumitra_session` is
domain-wide across `*.lumitra.co`, ANY signed-in Lumitra user from ANY company
has full admin access to social.lumitra.co today. This slice closes that.

**Scope is S2 only. Do NOT do S3 (the schema/company-scoping work) or S4
(erasure).** No schema change, no migration, in this slice.

## Read first

- `docs/plans/2026-08-16-multi-tenancy.md`, the whole file, S2 especially
- `src/lib/auth.ts` (what you are replacing)
- Every route under `src/app/api/` and `src/app/admin/` (each one's current guard)
- `src/lib/auth.test.ts` and `src/test/fake-prisma.ts` for the existing mocking
  conventions. Follow them; do not invent a second style.
- The installed package's own types after you add it:
  `node_modules/.pnpm/@marlinjai+auth-brain-nextjs@*/node_modules/@marlinjai/auth-brain-nextjs/dist/*.d.ts`.
  **Read them rather than assuming the API.** The single entry point is
  `createAuthBrainNextjs(config)`; it returns the middleware factory, session
  helpers and mutation guards.

## Definition of done

- `@marlinjai/auth-brain-nextjs@0.4.1` added as a dependency.
- One config seam (keep it in `src/lib/auth.ts` so imports stay stable):
  ```ts
  export const auth = createAuthBrainNextjs({
    appName: 'social',
    workspaces: { appGrant: { app: 'social' } },
    permissions: { 'social.edit': 'workspace.member' },
    publicPaths: ['/api/health'],
    publicUrl: 'https://social.lumitra.co',
  });
  ```
- `src/middleware.ts` exporting the package's auth middleware, with
  `export const runtime = 'nodejs'`.
- `requireAuth` (server components) and `requireApiAuth` (route handlers) keep
  their current NAMES and call shapes so existing call sites keep working, but
  are reimplemented on the package's session helpers.
- A verified session whose companies hold **no** `social` grant (the package
  reports `{ kind: 'none', reason: 'no-workspace-access' }`) lands on a
  `/no-access` page explaining that the company needs the Social Planner grant
  and who to ask. It must NEVER be a blank 500, and never silent access.
- `/api/health` stays public. Every other `/api/*` route and all of `/admin`
  require a granted session.
- Export the resolved **companyId** (`activeWorkspace.tenantId`) and the
  membership list from the session helper. Slice S3 consumes it. Do not use it
  for filtering yet, there is no company column to filter on.
- All env vars read lazily, never at module load, so `next build` works with no
  runtime secrets: `AUTH_BRAIN_URL`, `OPENFGA_API_URL`, `OPENFGA_STORE_ID`,
  `OPENFGA_AUTHORIZATION_MODEL_ID`, `OPENFGA_API_TOKEN`, `SERVICE_TOKEN`.
- Tests, with the package mocked (no network): no credential -> 401/redirect;
  valid session WITHOUT the grant -> `/no-access` (page) or 403/401 (API), and
  no data access; valid session WITH the grant -> passes; a bad bearer ->
  refused without falling through to the cookie path.
- Existing tests keep passing. Update them where the auth seam legitimately
  changed, but do NOT delete assertions or weaken them to make things green.
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit with a conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- **Do not touch the production database, Coolify, or Infisical.** The app is
  live at social.lumitra.co.
- Do not change `prisma/schema.prisma`. No migration in this slice.
- Do not build scheduling, publish queue, or Resend email.
- Do not weaken or delete existing tests to get a green build.

## Notes

- The auth-brain side (registering `social` in `SUITE_APPS`) is auth-brain PR
  #87, not yet merged. So at runtime today NO company holds the grant yet and
  everyone would land on `/no-access`. That is expected and correct: build and
  test against the mocked package. Do not add a bypass, an allowlist, or a
  "temporarily allow everyone" flag to work around it.
- Membership IS the gate: access comes from inviting an email to a workspace of
  a granted company in auth-brain's console, never an env allowlist here.
- The active-workspace cookie is a SELECTOR into the verified membership set,
  never a credential. The package validates it every request. Do not trust it
  for anything else, and never read a company id from a request body or query
  parameter.
- Never log the session cookie, the bearer token, or the verified session.
