---
task: mt-11
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-10]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-11** (section "MT-11 - Project-id-aware preview"): preview a SPECIFIC project at `/projects/<projectId>/preview` rather than relying on the single seeded in-memory project. Scoped + auth-gated like the editor route.

## Read first

- The MT-11 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- The current `/preview` route (`src/app/preview/`) — a client-only preview reading the in-memory current project (`rootStore.editorUI.currentProject` / current page). Understand how it renders the project (the `PreviewFrame` / preview client).
- `src/app/projects/[projectId]/page.tsx` + `EditorMount.tsx` (landed by MT-10) — mirror the server-load + client-mount pattern. `loadProject(scope, projectId)` + `getSnapshot`.
- Memory/project rule: pre-MVP, NO back-compat — replacing/redirecting the legacy `/preview` is fine.

## Definition of done

Create `src/app/projects/[projectId]/preview/page.tsx` (server component, `force-dynamic`):
- Resolve scope from the session (same helper as MT-09/MT-10); no session → redirect to login.
- `loadProject(scope, projectId)` (catch `SiteNotFoundError` → `notFound()`), serialize to a snapshot, and render the preview client (a `'use client'` mount, mirroring MT-10's `EditorMount` but rendering the preview frame for the loaded project's current/home page) with that snapshot. Reuse the existing preview-rendering client/component, fed the loaded project rather than the seeded in-memory one.
- Legacy `/preview`: keep it WORKING as a thin client redirect to `/projects/<currentProjectId>/preview` (read `rootStore.editorUI.currentProject?.id` client-side and `redirect`/`router.replace` to the id-aware route). This avoids a dead-end for the existing TopBar Preview button (which still points at `/preview`) until MT-12 updates the chrome. Do NOT touch `TopBar` here (MT-12 owns it).

Test:
- Assert previewing project A does not leak project B's content (e.g. the id-aware preview loader returns only project A's pages for A's id; extract a testable loader or an `.itest.ts`). Assert cross-workspace id → `notFound()`.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(projects): id-aware /projects/[projectId]/preview; legacy /preview redirects (MT-11)`.

## Constraints

- Stay in this worktree. Files: new `src/app/projects/[projectId]/preview/page.tsx` + its client mount; modify `src/app/preview/` to be a redirect shim. Do NOT touch `TopBar.tsx` (MT-12 owns it) — keeping `/preview` as a redirect is exactly what avoids needing to.
- Keep server-only imports out of any client mount (verify gate runs `next build`).
- Do not push to any remote. Output a final completion message.

## Notes

- If the existing preview client is tightly coupled to the in-memory store, the id-aware route can hydrate the loaded snapshot into the store (like the editor) and then render the same preview client. Reuse, don't fork, the preview rendering.
