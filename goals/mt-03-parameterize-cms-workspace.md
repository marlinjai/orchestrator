---
task: mt-03
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Implement spec **MT-03** (section "MT-03 - Parameterize the CMS workspace"): make every CMS read/write take an explicit `workspaceId` instead of the module constant `CMS_WORKSPACE_ID = 'framer-clone'` as the effective runtime workspace, so the render path (MT-13) and the auth-hardened write path (MT-14) can pass the per-request session workspace. Keep `CMS_WORKSPACE_ID` ONLY as a default value, never as a hard runtime pin inside a method body.

## Read first

- The MT-03 section of `docs/plans/2026-06-26-multi-tenancy-phase2-plan.md`.
- `src/lib/cms/constants.ts` — `CMS_WORKSPACE_ID = 'framer-clone'` (the SINGLE source of truth, re-exported server-side so client components never import a `server-only` module). Keep this export.
- `src/server/cms/repository.ts` — `getCmsRepository(): CmsReadRepository` (~line 306, returns the module-scope `repository`), `getCmsWriteRepository(): CmsWriteRepository` (~line 399). The FOUR places `CMS_WORKSPACE_ID` is used as the effective workspace: `~:255` `adapter.listTables(CMS_WORKSPACE_ID)` (listCollections), `~:347` `adapter.listTables(CMS_WORKSPACE_ID)` (createCollection uniqueness check), `~:355` `adapter.createTable({ workspaceId: CMS_WORKSPACE_ID, name })`, `~:374` `adapter.listTables(CMS_WORKSPACE_ID)` (rename-collision check).
- `src/server/cms/adapterClient.ts` — `getCmsAdapter(): PrismaAdapter` (~line 46), re-exports `CMS_WORKSPACE_ID` + `CMS_SCHEMA`.
- `src/server/cms/__tests__/actions.test.ts` (mocks `CMS_WORKSPACE_ID: 'test-ws'`) and any `repository*.test.ts` to see how the repo is tested.

## Definition of done

Parameterize the factory by workspace, defaulting to `CMS_WORKSPACE_ID` for back-compat (single tenant stays byte-identical):
- `getCmsRepository(workspaceId: string = CMS_WORKSPACE_ID): CmsReadRepository`
- `getCmsWriteRepository(workspaceId: string = CMS_WORKSPACE_ID): CmsWriteRepository`
- The returned repo's methods must close over the passed `workspaceId` and pass IT (not the module constant) into the four `adapter.listTables(workspaceId)` / `adapter.createTable({ workspaceId })` calls. Since the factory currently returns a shared module singleton, switch to constructing/binding a repo to the given `workspaceId` (a small per-call factory, or memoize per workspaceId in a Map). Existing callers that pass no argument behave identically (default).
- After this change, `grep -rn "CMS_WORKSPACE_ID" src/server/cms` shows it used ONLY as a default parameter value, NEVER as the effective workspace inside a method body.

Test (extend `actions.test.ts` area or add `src/server/cms/__tests__/repository.workspace.test.ts`):
- Mock/stub the adapter, then assert `getCmsRepository('ws-a').listCollections()` calls `adapter.listTables('ws-a')` and `getCmsRepository('ws-b').listCollections()` calls `adapter.listTables('ws-b')` — two different `workspaceId` args isolate `listTables` results.
- Assert the no-arg default still uses `CMS_WORKSPACE_ID`.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `refactor(cms): parameterize CMS repository by workspaceId, demote CMS_WORKSPACE_ID to default (MT-03)`.

## Constraints

- Stay in this worktree. Primary files: `src/server/cms/repository.ts`, `src/server/cms/adapterClient.ts`, `src/lib/cms/constants.ts` (keep the constant; only its ROLE changes), plus the new/extended test.
- Do NOT remove `CMS_WORKSPACE_ID` — it stays as the dev/seed default and the client-component prop default.
- The client components `src/components/cms/grid/CmsGrid.tsx` and `CmsWorkspaceOverlay.tsx` pass `workspaceId={CMS_WORKSPACE_ID}` — LEAVE them as-is (they keep the constant as their prop default for now; per-tenant client wiring comes later). Do NOT break them.
- Do NOT touch the interim admin secret, the render path, or the CMS routes — that is MT-13/MT-14. This spec is the repository parameterization ONLY.
- The unscoped by-id reads (`getCollection(id)`, `getRow`, `listRows`, `deleteCollection`) are out of scope here; do NOT try to scope them (MT-14 handles read-isolation).
- Do not push to any remote. Output a final completion message.

## Notes

- The whole point is that `getCmsRepository(site.workspaceId)` will become MT-13's call, and `getCmsWriteRepository(scope.workspaceId)` becomes MT-14's. Make the seam clean: a `workspaceId` arg with a default, threaded into the adapter calls.
- If you memoize per-workspace, do not leak state across tests — prefer constructing a fresh bound object per call unless there is a real perf reason (there isn't here).
