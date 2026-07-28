---
task: receipts-app-grant-door
depends_on: [authbrain-era3-convergence]
verify: pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint && pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Migrate the Receipts app's door from the legacy `receipts-` workspace-slug-prefix to the app-grant mode ("enter iff one of your companies holds the `receipts` grant"), WITHOUT changing how data is scoped (per auth-brain workspace UUID). Pre-launch gate item 6, receipts side.

## Precondition (run FIRST, abort loudly on failure)

`npm view @marlinjai/auth-brain-nextjs@0.2.0 version` must print `0.2.0` (the wrapper's new appGrant mode). If not, STOP and report.

## Read first

- `src/lib/auth.ts` (the ONE config: `workspaces: { slugPrefix: 'receipts-' }` becomes the appGrant mode per the 0.2.0 wrapper API)
- `src/lib/auth-workspace.ts` (`workspaceLabel` strips `receipts-` at :51; `sessionWorkspaceId`; dev bypass), `src/lib/auth-guards.ts`, `src/middleware.ts`
- `src/app/no-access/page.tsx` (copy says "not a member of any receipts workspace"; becomes "no company enabled for Receipts" guidance, no dead end)
- `scripts/migrate-workspace-id.ts` (the precedent for a data repoint script)
- `prisma/schema.prisma`: `DtTable.workspaceId` plus the four side tables keyed to auth-brain workspace ids (`SheetImportConfig.authWorkspaceId`, `WorkspaceVendorAttribution`, `OverviewSelection`, `WorkspaceNotes`)
- `src/lib/__tests__/auth-workspace.test.ts` (fixtures use `receipts-*` slugs; update)

## Definition of done

1. **Door flip**: `@marlinjai/auth-brain-nextjs` bumped to `^0.2.0`; `src/lib/auth.ts` switches to the appGrant mode with app slug `receipts`. Everything downstream (memberships, activeWorkspace cookie, guards, data scoping by workspace UUID) unchanged by construction. Dev bypass keeps working.
2. **Cosmetics de-prefixed**: `workspaceLabel` no longer assumes a `receipts-` prefix (label = workspace name/slug as-is, prefix stripped ONLY if present for back-compat display); no-access page copy updated to the company/grant vocabulary with a next action; README/doc prose updated.
3. **Data repoint script** `scripts/migrate-workspace-to-tenant-workspace.ts`: takes explicit `--map oldWorkspaceId=newWorkspaceId` pairs (NO hardcoded UUIDs), repoints `DtTable.workspaceId` and all four side tables in one transaction per pair, idempotent (already-repointed pairs no-op), prints per-table counts, refuses unknown flags. This is how existing data moves off the magic `receipts-*` workspaces before the operator deletes them. Unit-test the mapping logic with a mocked/ephemeral DB per the repo's test style.
4. **Test infrastructure** (the repo has none wired): add `"test": "vitest run"` and `"typecheck": "tsc --noEmit"` scripts; add door-level tests for the new mode (granted tenant -> its workspaces become memberships; ungranted -> no-access; zero-workspace granted tenant -> no-access not crash) using mocked verify payloads shaped by `@marlinjai/auth-brain-shared@^1.4.0`.
5. Existing behavior guarded: `SERVICE_TOKEN` machine path is explicitly UNCHANGED this slice (its migration to tenant-scoped keys is a recorded follow-up, not scope here).
6. `pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm lint && pnpm build` green. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push. Do not touch data-scoping semantics, the dt_* authorization chain, or the Google OAuth import flows.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.
