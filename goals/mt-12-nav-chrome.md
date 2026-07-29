---
task: mt-12
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-09, mt-07]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-12** (section "MT-12 - Editor/dashboard navigation chrome"): a "back to projects" link, a project-name display, an optional workspace selector in `TopBar`, and surfacing the publish live URL after publish.

## Read first

- The MT-12 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/components/TopBar.tsx` — observer component. Left zone = project title + page breadcrumb (static). MIDDLE zone (`<div className="flex-1" />`) = reserved empty space, the obvious extension point. Right zone = `<PublishButton />`, Preview button (`router.push('/preview')`), undo/redo, `HistoryMenu`.
- `src/components/PublishButton.tsx` — on success shows `Published N page(s)` from `payload.publishedPages.length`. The publish response now ALSO carries `subdomain` + `liveUrl` (landed by MT-07).
- `src/server/sites/scope.ts` — `resolveScopeForWorkspace(session, workspaceId)` supports a chosen workspace. `SessionVerifyResponse.workspaces` is the list.
- `src/lib/auth-api.ts` — `authenticateAccountRequest(req)` (session-only guard, no per-resource check) for the optional list endpoint. `listSites(scope)` from the repo.

## Definition of done

In `src/components/TopBar.tsx`:
- Show the current project name (already present — keep/clean it) and add a "back to /projects" control (a `next/link` to `/projects`).
- Update the Preview button target to the id-aware route: `/projects/<currentProjectId>/preview` (MT-11 landed it; the legacy `/preview` redirect still works, but point the button directly at the id-aware route when a current project exists).
- Workspace selector: WHEN the session has > 1 workspace, render a selector that re-scopes via `resolveScopeForWorkspace`. For D1 (personal workspace per user) most sessions have exactly 1 workspace, so this is HIDDEN by default — implement it conditionally and keep it minimal (it needs the session's workspaces client-side; fetch them from a small endpoint or accept them as a prop). If wiring the live session into the client TopBar is heavy, a minimal, correct conditional render (hidden at 1 workspace) satisfies the spec — do NOT over-build.

In `src/components/PublishButton.tsx`:
- After a successful publish, display "live at `<subdomain>.<base>`" using `payload.liveUrl` (fall back to `payload.subdomain` when `liveUrl` is null in local dev). Make it a clickable link to `liveUrl` when present. Keep the loud success/error surfacing.

OPTIONAL `src/app/api/projects/list/route.ts` (only if the workspace switcher / a client fetch needs it): `GET` using `authenticateAccountRequest` + a workspace-scoped `listSites`; returns ONLY the caller's sites. If you add it, test that it returns only the caller's sites (mirror the route-test mocking pattern).

Test:
- If you add `/api/projects/list`, assert it returns only the caller's sites and 401s without a session.
- A `TopBar`/`PublishButton` test (jsdom) asserting the live-URL surface renders from a publish response, and the back-to-projects link is present.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(editor): TopBar back-to-projects + workspace selector; surface publish live URL (MT-12)`.

## Constraints

- Stay in this worktree. Files: `src/components/TopBar.tsx`, `src/components/PublishButton.tsx`, optional new `src/app/api/projects/list/route.ts`, plus tests. This is the ONLY Wave-2 spec that restructures `TopBar`.
- Do NOT change the publish API response shape (MT-07 owns it) — only consume `liveUrl`/`subdomain`.
- Keep server-only imports out of client components (verify gate runs `next build`).
- Do not push to any remote. Output a final completion message.

## Notes

- Keep the workspace selector pragmatic. The hard requirement is back-to-projects + the live-URL surface; the selector is conditional and hidden for single-workspace users (the common D1 case). Don't block the spec on a heavy session-into-client plumbing.
