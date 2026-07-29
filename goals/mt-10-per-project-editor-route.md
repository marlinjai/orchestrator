---
task: mt-10
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
depends_on: [mt-04, mt-08]
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-10** (section "MT-10 - Per-project editor route"): `app.lumitra.co/projects/<projectId>` loads the real project SERVER-SIDE and hands the snapshot to the editor shell (MT-08's hydration). A cross-workspace id 404s, never another tenant's project.

## Read first

- The MT-10 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/server/sites/repository.ts` — `loadProject(scope, projectId): Promise<ProjectModelType>` (workspace-scoped; throws `SiteNotFoundError` on missing/cross-workspace). It returns a LIVE MST node; serialize with `getSnapshot(node)` (from `mobx-state-tree`) → `ProjectSnapshotOut`.
- `src/app/projects/page.tsx` (landed by MT-09) — copy its server-component session-resolution pattern (read `lumitra_session` via `next/headers` cookies → verify → `resolveActiveScope`; no/invalid session → redirect to auth-brain login with `return_to`). REUSE the same helper MT-09 introduced if it extracted one.
- `src/components/EditorApp.tsx` (landed by MT-08) — now accepts a `projectSnapshot` prop and hydrates it. `src/app/page.tsx` — the `ssr:false` client mount pattern to mirror.
- `src/components/PublishButton.tsx` — already publishes `rootStore.editorUI.currentProject` (which, after hydration, is the loaded project) to `/api/projects/publish`.
- `src/app/api/projects/save/route.ts` (landed by MT-04) — `POST /api/projects/save`.

## Definition of done

Create `src/app/projects/[projectId]/page.tsx` (SERVER component, `export const dynamic = 'force-dynamic'`):
- Resolve scope from the session (same pattern as MT-09's dashboard). No valid session → redirect to login.
- `const project = await loadProject(scope, params.projectId)` inside a try/catch; on `SiteNotFoundError` → `notFound()` (from `next/navigation`). NEVER render another tenant's project.
- Serialize: `const snapshot = getSnapshot(project) as ProjectSnapshotOut`.
- Render the client editor mount with that snapshot. Create `src/app/projects/[projectId]/EditorMount.tsx` (`'use client'`) that does the `dynamic(() => import('@/components/EditorApp'), { ssr: false })` and renders `<EditorApp projectSnapshot={snapshot} />`. The server page renders `<EditorMount projectSnapshot={snapshot} />`.
- Save/publish target the loaded id: Publish already does (via `currentProject`). Add a minimal Save affordance so saves go to `/api/projects/save`: either a small `SaveButton` (mirror `PublishButton`: `getSnapshot(currentProject)` → `POST /api/projects/save`, surface success/error loudly) rendered in the editor, OR confirm an existing save path targets the loaded id. Do NOT make saving publish.

Test (integration or extracted-loader unit):
- Load a seeded project by id and assert the rendered shell / serialized snapshot carries THAT project's pages (e.g. extract `loadProjectSnapshot(scope, id)` and unit-test it; or an `.itest.ts`). Assert a `projectId` not in the caller's workspace yields `notFound()` (the loader throws `SiteNotFoundError`).

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(projects): /projects/[projectId] server-loads + hydrates the editor (MT-10)`.

## Constraints

- Stay in this worktree. Files: new `src/app/projects/[projectId]/page.tsx`, new `EditorMount.tsx`, optional new `SaveButton.tsx`, optional extracted loader + test. You MAY lightly touch `PublishButton.tsx` ONLY if needed to confirm it targets the loaded id (it should already). Do NOT restructure `TopBar` (MT-12 owns it).
- Do NOT build the preview route (MT-11) or the nav chrome (MT-12).
- Keep server-only imports out of the client mount (`next build` catches violations; the verify gate runs build).
- Do not push to any remote. Output a final completion message.

## Notes

- The server-component-session helper: if MT-09 extracted a reusable `requireSessionScope()`-style helper, reuse it; otherwise replicate the cookie-read + verify + resolveActiveScope inline (fail-closed: redirect on no session).
- `getSnapshot` on the loaded MST node gives a `SnapshotOut` that EditorApp's `projectSnapshot` prop ingests.
