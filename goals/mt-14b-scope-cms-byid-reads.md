---
task: mt-14b
spec: docs/plans/2026-06-26-multi-tenancy-phase2-plan.md
verify: pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Close the MT-14 residual: scope the CMS by-id reads by workspace. After MT-14, the CMS WRITE path is session-scoped, but the by-id READS (`getCollection(id)`, `getRow(id, rowId)`, `listRows(id, query)`) in `src/server/cms/repository.ts` operate by table/row id with NO workspace filter — a defense-in-depth cross-tenant read gap (reachable only with a known uuid, but it should not be reachable at all across tenants).

## Read first

- `src/server/cms/repository.ts` — `getCmsRepository(workspaceId)` / `getCmsWriteRepository(workspaceId)` are now bound to a `workspaceId` (MT-03). The read methods `getCollection(id)`, `getRow(id, rowId)`, `listRows(id, query)` resolve a table/row by id WITHOUT checking it belongs to the bound workspace. Note: `getRow` already guards `row.tableId === id`; extend that pattern to the WORKSPACE boundary.
- `src/server/cms/adapterClient.ts` — `getCmsAdapter()` and the `PrismaAdapter`. Check what the adapter's `getTable(id)` / `getRow` return — they should expose the table's `workspaceId` (the `DtTable` model carries `workspace_id` + `tenant_group_id`, the CMS hard-isolation boundary).

## Definition of done

- The repo is bound to `workspaceId`. Make every by-id read assert the resolved table belongs to that workspace: `getCollection(id)` returns null (or throws the typed `CmsNotFoundError`) when the table's `workspaceId !== boundWorkspaceId`; `getRow(id, rowId)` and `listRows(id, query)` likewise refuse a table outside the bound workspace. Use whichever the adapter exposes (the table's `workspaceId`); if the adapter doesn't surface it, add a minimal accessor or filter `getTable` by workspace.
- Missing-vs-cross-workspace must be INDISTINGUISHABLE (return the same not-found result; never leak existence), mirroring the `SiteRepository` boundary convention.
- A test asserts: `getCmsRepository('ws-a').getCollection(<ws-b table id>)` returns null/not-found; same for `getRow`/`listRows`. The same-workspace reads still work.

Plus: `pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm build` pass; single conventional commit e.g. `fix(cms): scope by-id reads to the bound workspace (close MT-14 read-isolation gap)`.

## Constraints

- Stay in this worktree. Files: `src/server/cms/repository.ts`, possibly `src/server/cms/adapterClient.ts`, plus tests. Do NOT change the write path (MT-14 owns it) or the workspace parameterization (MT-03).
- Keep single-tenant behavior identical (same-workspace reads unchanged).
- Do not push to any remote. Output a final completion message.

## Notes

- This is small + focused. The bound `workspaceId` is already threaded by MT-03's factory; you only need to enforce it on the read methods that currently skip it.
