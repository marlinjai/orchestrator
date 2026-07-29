---
task: mt-09
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-05]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-09** (section "MT-09 - Per-user/workspace projects dashboard route"): a server-component dashboard at `/projects` listing only the caller's projects, with a "New project" button. Per-user isolation comes from D1 (each user gets a personal workspace from auth-brain; zero schema change).

## Read first

- The MT-09 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/lib/auth-api.ts` — `getVerifiedSession(req: Request)` reads the `lumitra_session` cookie off a raw `Cookie` header. In a SERVER COMPONENT there is no `Request`; read the cookie via `next/headers` `cookies()` and verify it. FIRST search the repo for an existing server-component session reader (grep `next/headers`, `cookies()`, `getVerifiedSession`, `verifySession` across `src/`); if one exists, use it. If NONE exists, read `(await cookies()).get('lumitra_session')?.value` and call `authBrainClient.verifySession(value)` directly (mirror `getVerifiedSession`'s internals; `authBrainClient` is in `src/lib/auth-brain.ts`), then `resolveActiveScope(session)`.
- `src/server/sites/scope.ts` — `resolveActiveScope(session)` → `{ ok, scope }`. `src/server/sites/repository.ts` — `listSites(scope): Promise<SiteSummary[]>` (`SiteSummary = { siteId, name, description, status, lumitraEnabled, createdAt, updatedAt }`), workspace-scoped. `getSiteRepository()`.
- `src/lib/auth-brain.ts` — `AUTH_BRAIN_URL` fallback `'https://auth.lumitra.co'`.
- `src/app/api/projects/route.ts` (landed by MT-05) — `POST /api/projects` returns `{ siteId }` for the New-project button.
- Existing app layout/components for styling conventions (`src/app/layout.tsx`, UI primitives under `src/components/ui`).

## Definition of done

Create `src/app/projects/page.tsx` (server component, `export const dynamic = 'force-dynamic'`):
- Resolve the session from `next/headers` cookies (see above). If NO valid session OR `resolveActiveScope` fails → `redirect()` (from `next/navigation`) to `${AUTH_BRAIN_URL}/login?return_to=<absolute dashboard URL>` (build `return_to` from the request headers' host + `/projects`; consistent with the middleware bounce contract).
- With a valid scope: `listSites(scope)` and render one entry per site — a link to `/projects/<siteId>` showing `name`, `status`, and `updatedAt`. Empty state: a friendly "no projects yet" with the New-project affordance.
- A "New project" control: a SMALL client component (`'use client'`, colocated e.g. `src/app/projects/NewProjectButton.tsx`) that `POST`s to `/api/projects` (optionally `{ name }`), then `router.push('/projects/<newId>')` from the `{ siteId }` response. Surface errors (never silent).
- The dashboard NEVER reads a client-supplied workspace — scope is server-derived.

Test (mirror existing patterns; server components are awkward to render, so prefer either an extracted data-loader unit test or an integration test):
- Assert a session for workspace A sees ONLY workspace-A sites (e.g. extract the list-loading into a testable function that takes a scope and asserts `listSites` is called workspace-scoped; or an `.itest.ts` seeding two workspaces and asserting isolation). Assert the no-session path redirects to the auth-brain login with a correct `return_to`.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(projects): per-workspace /projects dashboard with New-project (MT-09)`.

## Constraints

- Stay in this worktree. Files: new `src/app/projects/page.tsx`, new `src/app/projects/NewProjectButton.tsx` (or similar), optional small extracted loader + test. Do NOT touch the middleware matcher (that is MT-16) — this page self-guards via the redirect.
- Do NOT create `/projects/[projectId]` (that is MT-10). Only the list route here.
- Keep server-only imports OUT of the client button (`next build` will catch a boundary violation — the verify gate runs build).
- Do not push to any remote. Output a final completion message.

## Notes

- This is the spec most likely to hit the client/server boundary. The page is a server component (reads cookies, calls the server-only repo). The New-project button is a separate client component. Keep the import graph clean.
- If you read the cookie directly, mirror `getVerifiedSession`'s fail-closed behavior (null cookie / failed verify → treat as unauthenticated → redirect, never throw a 500 page).
