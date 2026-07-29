---
task: framer-publish-write
spec: docs/specs/build-2026-06/hosted-demo/hosted-page-demo.md
verify: DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Build the **publish write path**: a guarded `POST /api/projects/publish` that serializes the live MST
project to the persisted `Site` + `SitePage` rows, plus a **Publish** button in the editor top bar that
calls it and surfaces success/failure loudly. This is build items #1-#2 of the hosted-page demo plan,
RECONCILED to the P1 foundation that already shipped persistence.

## CRITICAL reconciliation (read before building — the demo plan is partly superseded)

The demo plan (item #1) proposed a NEW `PublishedSite` Prisma model. That is SUPERSEDED: P1 already
shipped the canonical persistence layer. **DROP the `PublishedSite` proposal entirely.** Build on what
exists:

- `src/server/sites/repository.ts` -> `getSiteRepository()` already implements
  `saveProject(scope, project)`: it serializes the MST `ProjectModel` (via `projectToPersisted` in
  `snapshot.ts`), upserts the `Site` row, and reconciles `SitePage` rows in one transaction, stamping
  `workspace_id` + `tenant_group_id` on every row. **Reuse this; do NOT write a new persistence path.**
- `saveProject` deliberately PRESERVES `Site.status` on update ("publish/archive own it"). So publish
  needs to ALSO transition `Site.status` to a published state. Add a small, scoped repository method for
  that (e.g. `publishProject(scope, siteId)` or a `status` param on save) that sets
  `Site.status = 'published'` (the `SiteStatus` enum + `status` column ALREADY exist on the P1 model —
  do NOT add a schema field). NO `prisma/schema.prisma` change and NO migration in this slice.

## Auth: real auth-brain `publishSite`, NOT the interim admin-secret stub

- The publish endpoint is **admin-guarded via auth-brain**: `authenticateRequest(req, workspaceId,
  'publishSite')` from `src/lib/auth-api.ts` (the `publishSite` permission already exists in
  `src/lib/permissions.ts` -> `FRAMER_PERMISSIONS`, requiring workspace.admin). This is the P1-correct
  guard and it is what gives you a REAL session to derive the tenant scope from.
- Resolve the `TenantScope` (the `{ workspaceId, tenantGroupId }` `saveProject` requires) from the
  VERIFIED session via `resolveScopeForWorkspace(session, workspaceId)` / `resolveActiveScope(session)`
  in `src/server/sites/scope.ts` — NEVER from anything the client sends, NEVER the interim
  `ws_interim_default` constant. The whole point of P1's hard-isolation contract is that the scope comes
  from the server-verified session.
- Do NOT use `src/server/auth/guard.ts`'s `requireAdmin` / interim `can()` stub for THIS endpoint. That
  stub (`return principal.isAdmin`, constant `INTERIM_WORKSPACE_ID`, no tenant_group) is the interim
  data-write guard and cannot produce a valid `TenantScope`.

### Secondary (audit, scoped — do NOT expand into a migration): verify CMS/commerce writes are gated

The handoff asks to "verify the auth-brain integration actually gates CMS+commerce writes (replace any
can() stub usage)". Scope this TIGHTLY: (1) confirm the publish endpoint you build uses the REAL
auth-brain `can()`/`publishSite`, never a permissive stub; (2) AUDIT (read-only) whether the existing
CMS/commerce write routes still rely on the interim `requireAdmin` + stub `can()` in
`src/server/auth/guard.ts`. They DO, by current design (guard.ts documents "real auth-brain integration
P2/E7 out of scope"). Migrating that whole surface is a SEPARATE slice and WOULD COLLIDE with the
content-agent slice in flight (which is actively adding interim-admin-guarded routes). So do NOT migrate
it here. Instead file ONE `open_thread` describing the interim->auth-brain migration of the CMS/commerce
write routes as a follow-up slice, with the file list. (This is the documented scope-expansion exception
to the no-tech-debt rule.)

## Read first

- `docs/specs/build-2026-06/hosted-demo/hosted-page-demo.md` (items #1-#2 + the "Decided scope" and
  "Test plan" sections; ignore the `PublishedSite` model name per the reconciliation above).
- `src/server/sites/repository.ts` (`getSiteRepository`, `saveProject`, `loadProject`, the `TenantScope`
  + hard-isolation contract), `src/server/sites/snapshot.ts` (`projectToPersisted`), `scope.ts`
  (`resolveScopeForWorkspace` / `resolveActiveScope`), `index.ts` (barrel).
- `src/lib/auth-api.ts` (`authenticateRequest`, the 401/403 result shape), `src/lib/permissions.ts`
  (`FRAMER_PERMISSIONS`, `publishSite`, `FramerAction`).
- An existing guarded route for the pattern: `src/app/api/cms/collections/route.ts` and the commerce
  write routes under `src/app/api/commerce/` (response envelope via `src/lib/api/respond.ts`).
- The editor top bar: `src/components/TopBar.tsx` (where the Publish button goes) and `EditorApp.tsx`
  (how it gets the active project / store). The MST store / `ProjectModel` is the working copy to
  serialize — find how the editor accesses the current `ProjectModel` instance and its
  `workspaceId`/site id.

## Definition of done

- `POST /api/projects/publish` (admin-guarded via auth-brain `publishSite`): accepts the project
  snapshot (or resolves it server-side from the editor's persisted working copy — pick the approach that
  matches how the editor already saves), resolves the real `TenantScope` from the verified session,
  calls `saveProject(scope, project)` then transitions `Site.status` to published, and returns a clear
  success envelope (published site id + the resolved public path/subdomain if known) or a loud,
  structured error. 401 when unauthenticated, 403 when not a workspace admin, 400 on a malformed body.
- A **Publish** button in `TopBar.tsx` that calls the endpoint, shows in-flight state, and surfaces
  success (e.g. a toast/confirmation with the published path) AND failure (the error message, never a
  silent no-op). Cover the unhappy paths: not-admin (403), network failure, validation failure.
- Headless tests (`.test.ts(x)`): the publish route round-trips a project snapshot through
  `saveProject` (assert the `Site`/`SitePage` rows written + status -> published); admin-guarded (401 no
  session, 403 non-admin); upsert-by-id within the workspace (a second publish updates, not duplicates);
  cross-workspace publish of a foreign site id is rejected. Button test: click calls the endpoint and
  renders success + error states. Mock Prisma + the auth-brain client following the repo's existing test
  patterns (see `src/app/api/cms/__tests__/` and `src/server/sites/__tests__/`).
- `DATABASE_URL='postgresql://x:x@localhost:5432/x' pnpm exec prisma generate && pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` all green.
- Flip the `hosted-page-demo.md` frontmatter only if you are completing the WHOLE plan — you are not
  (renderer + infra remain), so leave its status as-is; instead note in the PR which items (#1-#2) this
  slice lands.
- Single commit, conventional-commit message describing the WHY.

## Constraints

- NO `prisma/schema.prisma` change, NO migration (the P1 `Site`/`SitePage`/`SiteStatus` models suffice).
  This keeps the slice parallel-safe with the content-agent slice that holds the prisma lock. If you
  believe a schema change is required, STOP and escalate rather than editing the schema.
- Studio design tokens only for the Publish button (reuse `src/components/ui/*`); match the existing
  TopBar styling. No hardcoded gray/blue/red.
- Production-grade: errors surface loudly (no swallowed publish failures); cover unhappy paths. Zero
  tech debt EXCEPT the one explicitly-deferred CMS/commerce-write auth migration (file it as an
  `open_thread`, do NOT half-do it).
- No em-dashes or en-dashes anywhere (code, comments, commit, PR-relevant strings).
- Stay in this worktree. Do not push to any remote (the operator handles PR + merge). Do not run
  destructive commands. When done, output a final completion message listing files changed and the
  filed `open_thread`.

## Notes

- This slice is parallel-safe (no prisma/migration shared_state). It pairs with `framer-server-renderer`
  (the READ side): publish WRITES `SitePage` snapshots, the renderer READS them. Both rely on the SAME
  `snapshot.ts` contract already on main, so they do not depend on each other's code.
- If the editor already persists the working copy via an existing save path (auth-brain-guarded
  `/api/sites/*`), publish can simply mark the already-saved site published + flip status, rather than
  re-serializing. Inspect how the editor saves today before choosing; prefer reusing the existing save
  over duplicating serialization.
