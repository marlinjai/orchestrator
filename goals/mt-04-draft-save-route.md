---
task: mt-04
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-04** (section "MT-04 - Draft-save route"): a `POST /api/projects/save` that persists the editor working copy WITHOUT publishing. Today `/api/projects/publish` is the only persistence path and it always flips to `published`, so a loaded real project cannot be edited and saved without going live. This route MUST land before load-by-id (MT-10) or every save is destructive.

## Read first

- The MT-04 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/app/api/projects/publish/route.ts` — MIRROR this file's structure EXACTLY. Note its zod `projectSnapshotSchema`/`publishBodySchema` (`.passthrough()` at every level), the `runtime='nodejs'` + `dynamic='force-dynamic'` exports, and the EXACT guarded flow:
  1. `const session = await getVerifiedSession(req); if (!session) return jsonError('unauthorized', 'authentication required', 401);`
  2. `const scopeResult = resolveActiveScope(session); if (!scopeResult.ok) return jsonError('no_active_workspace', 'no active workspace to save into', 403); const { scope } = scopeResult;`
  3. `const auth = await authenticateRequest(req, scope.workspaceId, 'editSite'); if (!auth.authenticated) return jsonError(auth.status === 401 ? 'unauthorized' : 'forbidden', auth.error, auth.status);`
  4. `const body = await parseBody(req, publishBodySchema); if (!body.ok) return body.response;`
  5. `repo.saveProject(scope, project)` ONLY — NEVER `publishProject`.
- `src/server/sites/repository.ts` — `saveProject(scope, project)` PRESERVES `Site.status` on update (its update block omits `status`), so saving a draft keeps it draft and saving a published site keeps it published. `getSiteRepository()` is the lazy singleton. `SiteNotFoundError` / `SiteRepositoryError` live in `src/server/sites/errors.ts`; map them with `siteRepositoryErrorResponse(err)`.
- `src/lib/api/respond.ts` — `jsonError(code, message, status)` → `{ error: { code, message } }`, and `parseBody`.
- `src/app/api/projects/__tests__/publish-route.test.ts` — MIRROR this test's mocking pattern (see Notes).

## Definition of done

Create `src/app/api/projects/save/route.ts`:
- `export const runtime = 'nodejs'; export const dynamic = 'force-dynamic';`
- Reuse the SAME body schema as publish (import/export-share the `projectSnapshotSchema` if it's exported from the publish route or a shared module; otherwise duplicate the identical schema — prefer extracting it to a shared module like `src/app/api/projects/_schema.ts` and importing from both, but do NOT change publish's behavior).
- `POST(req)`: the guarded flow above, authorizing `editSite` (which requires `workspace.admin` per `FRAMER_PERMISSIONS`). Call `repo.saveProject(scope, project)` and NOTHING else (no publish).
- Success: `Response.json({ siteId: project.id, savedPages })` where `savedPages = Object.values(body.data.project.pages).map(p => p.slug ?? '')` (mirror publish's `publishedPages`). Do NOT claim a status (save does not change it).
- Failure envelope mirrors publish EXACTLY: 401 (no session / auth 401), 403 (no active workspace / forbidden), 400 (bad_json / bad_body from parseBody, invalid_tenant_scope), 404 (site_not_found cross-workspace), 500 (`save_failed`).

Create `src/app/api/projects/__tests__/save-route.test.ts`:
- Mirror `publish-route.test.ts`. Assert: a valid editSite session saves (calls `saveProject` with the server-derived scope), `publishProject` is NEVER called, 401 on no session, 403 on no active workspace / non-admin, 400 on bad body, 404 on cross-workspace id (repo throws `SiteNotFoundError`). Assert scope comes from the session, never the body.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `feat(api): non-destructive POST /api/projects/save (draft persistence) (MT-04)`.

## Constraints

- Stay in this worktree. New files only, plus an OPTIONAL shared schema extraction (`src/app/api/projects/_schema.ts`) imported by both publish and save — if you extract, publish route behavior MUST stay identical and its tests MUST still pass.
- Do NOT add a subdomain allocator or any publish behavior. This is save-only.
- Do not push to any remote. Output a final completion message.

## Notes

- Route test gotcha: route tests default to the jsdom vitest project. Add `// @vitest-environment node` as the FIRST line. Mock `@/lib/auth-brain` (`verifySession`, `can`), keep `resolveActiveScope` REAL, and `vi.mock('@/server/sites', ...)` spreading the actual module and overriding ONLY `getSiteRepository`. Session cookie via `headers['cookie'] = 'lumitra_session=good'`; no-session via `cookie: null`.
- `editSite` and `publishSite` both require `workspace.admin`, so the auth assertions match publish's, only the action string differs.
