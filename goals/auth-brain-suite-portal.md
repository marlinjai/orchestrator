---
task: auth-brain-suite-portal
spec: docs/superpowers/plans/2026-06-12-suite-portal.md
verify: pnpm test
verify_fix_cap: 3
verify_timeout_s: 1500
marlin_proxy: live
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

Implement the **suite portal** on the auth-brain root page per the spec at `docs/superpowers/plans/2026-06-12-suite-portal.md`: replace the placeholder `/` with a session-gated app launcher (greeting, app cards from an in-code registry, tenants/workspaces summary, settings link, sign-out), redirecting logged-out visitors to `/login`. The spec's Decisions section is settled; do not relitigate.

## Read first

- The spec in full: `docs/superpowers/plans/2026-06-12-suite-portal.md`.
- The pattern to mirror EXACTLY for session gating + data loading: `packages/app/src/app/settings/account/page.tsx` (force-dynamic, `cookies()` + `loadEnv` + `verifySessionToken` + `findUserById` / `listTenantsForUser` / `listWorkspacesForUser`, redirect on missing session). Note its email-verification banner; reuse that pattern.
- The current placeholder you are replacing: `packages/app/src/app/page.tsx`.
- How sign-out works on the existing settings surface (find the existing logout control/route and reuse it; do NOT invent a new logout path).
- The RTL + jsdom test harness from PR #23: find the existing page/component specs under `packages/app/src` and mirror their mocking approach (session, repos) for the new portal specs.
- Repo conventions: root `pnpm test` / `typecheck` / `lint` (husky runs typecheck+lint on commit), no em/en-dashes, conventional commits.

## Definition of done

1. `packages/app/src/lib/suite-apps.ts` exporting the typed `SUITE_APPS` registry with the two entries from the spec (studio, analytics).
2. Root `page.tsx` is the portal per the spec's Scope: session-gated, greeting (name -> email fallback), verification banner for unverified users, app cards linking out, tenants + workspaces summary with roles, footer with `/settings/account` link + the existing sign-out control.
3. Logged-out `/` redirects to `/login` (no return_to; the callback's `/` fallback closes the loop).
4. Tests (RTL + jsdom, mocked session/repos, no live DB, no network): cards render for each registry entry; redirect happens with no session; banner shows for unverified email.
5. No new dependencies, no Prisma/SQL schema changes, no env additions, no changes to OAuth/session/logout logic itself.
6. Root `pnpm test` GREEN (the verify gate), typecheck + lint clean.
7. Single conventional commit on this branch describing the WHY (the root was a dead-end placeholder; the post-login `/` fallback needs a real front door).

## Constraints (hard, do not violate)

- Do NOT touch the OAuth routes, session verification, cookies, middleware, or admin console. You consume the session, never alter how it is established.
- Do NOT add per-app entitlement logic, a workspace switcher, or OpenFGA calls (later slices; note as `open_thread` if tempted).
- Do NOT deploy, push, or touch secrets. Stay in this worktree; the operator handles push/PR/merge.
- Styling: match the existing minimal Tailwind look of the auth pages (neutral palette, simple cards). No new UI libraries.
- No em-dashes or en-dashes anywhere. Report via `update_state` (`file_touched`, `decision`, `open_thread`, `commit`).

## Notes

- The repo's test suite runs without a live database (CI runs it on bare runners); if a spec you mirror does reach for a DB, mock at the repository-function boundary like the existing specs do.
- If the existing settings surface has no reusable sign-out CONTROL (only a route), a minimal form/anchor posting to the existing logout route is fine; record the choice as a `decision`.
