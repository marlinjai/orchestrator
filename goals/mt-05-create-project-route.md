---
task: mt-05
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-05** (section "MT-05 - Create-project route"): a `POST /api/projects` that creates a new empty DRAFT site row in the caller's active workspace and returns its id, so the dashboard's "New project" button (MT-09) has something to call. Today `createProject` is a client-only MST action; no server create exists.

## Read first

- The MT-05 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/app/api/projects/publish/route.ts` — mirror its guarded flow + error envelope (getVerifiedSession → resolveActiveScope → authenticateRequest → repo call).
- `src/server/sites/repository.ts` — `saveProject(scope, project)` accepts EITHER a live `ProjectModelType` OR a snapshot (`Parameters<typeof projectToPersisted>[0]`). On CREATE (upsert create block) it sets NO `status`, so the row defaults to `draft`. It stamps `workspaceId`/`tenantGroupId` from `scope`.
- `src/server/sites/snapshot.ts` — `projectToPersisted` (the OUT path). `persistedToProjectSnapshot` (the IN path).
- `src/models/ProjectModel.ts` — `ProjectModel`, `ProjectSnapshotOut`/`ProjectSnapshotIn` (lines ~284-285). `PageModel`. Determine the MINIMAL valid project snapshot: one page with `slug: ''` (home). The publish zod schema requires `id`, `metadata{title, description?, createdAt:number, updatedAt:number}`, `pages` record. Each page persists as `{ pageId, slug, snapshot }` where `snapshot` is a full `PageSnapshotOut`.
- `src/stores/ProjectStore.ts` `createProject` — for reference ONLY; it builds a HEAVY demo tree you must NOT reuse. You want a minimal empty home page, not the demo.

## Definition of done

Create `src/app/api/projects/route.ts`:
- `export const runtime = 'nodejs'; export const dynamic = 'force-dynamic';`
- `POST(req)` with an OPTIONAL `{ name?: string }` body (validate with a small zod schema; tolerate empty body). Guarded flow authorizing `editSite` (workspace.admin), scope from `resolveActiveScope(session)`.
- Mint `const siteId = crypto.randomUUID()` SERVER-SIDE. Build a MINIMAL valid draft `ProjectModel` snapshot with `id: siteId`, `metadata.title = name ?? 'Untitled Project'`, timestamps = `Date.now()`, and exactly ONE home page (`slug: ''`). Determine the minimal-valid `PageSnapshotOut` by reading `PageModel`/`ProjectModel`; you MAY build it by `ProjectModel.create(<minimal snapshot>)` then `getSnapshot(node)` to guarantee validity, or construct the persisted shape directly. Persist via `repo.saveProject(scope, <snapshot>)`. Do NOT call `publishProject`.
- Success: `Response.json({ siteId })`.
- Failure envelope mirrors publish: 401 / 403 / 400 / 500 (`create_failed`).

Create `src/app/api/projects/__tests__/create-route.test.ts`:
- Mirror `publish-route.test.ts` mocking. Assert: a valid editSite session creates a row (calls `saveProject` with the server-derived scope and a snapshot whose `id` is a freshly-minted uuid and whose pages contain exactly one `slug:''` home page), returns `{ siteId }`, status defaults to draft (saveProject create-path omits status). Assert 401 no session, 403 no active workspace / non-admin, 400 bad body.
- If a Docker daemon is available, ALSO add an integration test (`*.itest.ts`) asserting two different sessions create rows in DIFFERENT workspaces and neither can `loadProject` the other's id (`SiteNotFoundError`). If Docker is not available locally, write the `.itest.ts` anyway (CI runs `pnpm test:integration` with testcontainers) but do NOT block your in-loop verify on it.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(api): POST /api/projects mints an empty draft site in the active workspace (MT-05)`.

## Constraints

- Stay in this worktree. New files only (`route.ts` + tests). You MAY add a tiny helper for the minimal snapshot, but keep it local to this route or `src/server/sites/`.
- Do NOT reuse the heavy demo tree from `ProjectStore.createProject`. The created draft should be genuinely minimal (one empty home page).
- Do not push to any remote. Output a final completion message.

## Notes

- Route test gotcha: add `// @vitest-environment node` as the first line. Same mocking pattern as MT-04: mock `@/lib/auth-brain`, keep `resolveActiveScope` real, mock only `getSiteRepository`.
- The created row's `status='draft'` is the DB default (saveProject's create block omits status). Do NOT pass an explicit status.
- `crypto.randomUUID()` is available in the Node runtime (no import needed).
