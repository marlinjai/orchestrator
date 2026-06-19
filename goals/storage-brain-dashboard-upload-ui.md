---
task: storage-brain-dashboard-upload-ui
spec: docs/plans/2026-06-16-storage-brain-dashboard-upload-ui.md
shared_state: [lockfile]
verify: pnpm run build && pnpm run typecheck && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal

Implement the leaf spec at `docs/plans/2026-06-16-storage-brain-dashboard-upload-ui.md`: add an
upload UI (dropzone + dialog, progress, cancel, unhappy-path handling) to the Storage Brain
dashboard files page. Because the admin SDK has NO upload method today, this slice adds an
**admin-scoped upload-request endpoint** on the API so the dashboard uploads with the admin
credential it already holds (never a tenant key). This is the original feature: upload files to
buckets from the dashboard.

## Read first

- The spec in full (the core problem, the admin-endpoint design decision, browser-direct PUT +
  CORS, the dashboard route, the UI, unhappy paths, file list, tests).
- Existing code to extend, not break:
  - `packages/api/src/routes/upload.ts` (tenant upload-request: extract its validation/quota/
    handshake into a shared helper and call it from BOTH the tenant route and the new admin route)
  - `packages/api/src/routes/admin.ts` + `src/app.ts` (admin route registration + auth)
  - `packages/api/src/routes/internal-upload.ts` (the presigned PUT target; add CORS for the
    dashboard origin)
  - `packages/sdk/src/admin.ts` (`StorageBrainAdmin`; add `requestTenantUpload`)
  - dashboard files page `src/app/(dashboard)/tenants/[tenantId]/files/page.tsx`, the existing
    modal/form components (`components/ui/ConfirmModal.tsx`, `components/tenants/CreateTenantModal.tsx`),
    `hooks/useFiles.ts`, and the workspaces route `src/app/api/tenants/[id]/workspaces/route.ts`
  - `packages/shared/src/schemas.ts` (`requestUploadSchema`, `MAX_FILE_SIZE_BYTES`)
- Test conventions: `packages/*/src/**/*.spec.ts` (vitest, mock DB/storage, `app.request(...)`).

## Definition of done

Everything in the spec body, plus:

- `pnpm run build && pnpm run typecheck && pnpm test` all green. (Do NOT run/fix `pnpm lint`: the
  repo has ~199 PRE-EXISTING lint errors tracked separately; just keep YOUR new files clean.)
- The shared upload helper is used by both the tenant and the new admin route (no copy-paste);
  a test asserts both routes validate identically for the same inputs.
- Admin upload-request route: success returns a handshake; invalid-type/too-large/tenant-quota/
  workspace-missing/workspace-quota each map to the right status; 401 without the admin key.
- UploadDialog: progress from a mocked XHR, cancel aborts, every unhappy path renders a message
  (none swallowed). Success refreshes the files list.
- Spec frontmatter `status: draft` -> `status: done`.
- Single feature commit (a second commit is fine; they squash), conventional message with WHY.

## Constraints

- Stay in this worktree. Do not push. Additive/non-breaking: the tenant `upload.ts` behavior must
  be unchanged after the helper extraction (its tests still pass).
- Do NOT fetch or expose a tenant API key in the dashboard; the dashboard uploads via the
  admin-scoped endpoint using the admin credential from `getAdmin()`.
- Keep the 100MB `MAX_FILE_SIZE_BYTES` limit; do not raise it or add multipart/resumable.
- No service-account-key/auth-brain work (deferred), no per-tenant `can()` filtering.
- No em-dashes or en-dashes in any code/comment/doc.

## Notes

- The dashboard is Next.js 15 App Router on Node; the API is Hono on Cloudflare Workers (the
  admin route + CORS change live there).
- Prefer browser-direct PUT to the presigned URL (XHR progress + AbortSignal). If CORS on the
  internal upload route proves impractical, fall back to a dashboard server proxy route and note
  it as an `open_thread`.
- File any genuinely out-of-scope discovery as an `open_thread`, not a bare TODO.
