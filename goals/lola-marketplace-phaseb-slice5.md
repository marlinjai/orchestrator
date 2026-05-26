---
task: lola-marketplace-phaseb-slice5
spec: docs/specs/2026-05-26-marketplace-phaseb-slice5-admin-crud-endpoints.md
depends_on: [lola-marketplace-phaseb-slice3]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice5-admin-crud-endpoints.md` end-to-end. Adds the admin-side CRUD endpoints for marketplace stories: create, update, publish, archive, list-jobs. All gated by the existing admin auth guard (admin email per memory `user_admin_email`). Hard DELETE only allowed when no `LibraryEntry` references the story; otherwise 409 with an instruction to archive.

## Read first

- The spec file in full
- The parent plan section "API Surface -> Admin" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- `apps/api/src/modules/admin/admin.controller.ts` and `admin.module.ts` (existing admin auth guard pattern; mirror it)
- `apps/api/src/modules/marketplace/marketplace-stories.service.ts` (slice 3 service; extend or compose, don't duplicate read logic)
- The four marketplace Prisma models in `apps/api/prisma/schema.prisma`
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/api test` passes
- `pnpm --filter @lola/api tsc --noEmit` clean
- `pnpm build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(api): admin marketplace CRUD endpoints`)

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- Every admin endpoint MUST require the existing admin auth guard. Add a co-located guard-passes / guard-rejects test pair for at least one endpoint to prove the wiring.
- Hard DELETE returns 409 (Conflict) with `{error: 'has_library_references', message: 'Archive instead'}` when any `LibraryEntry.marketplaceStoryId` references the row. Verify with a unit test.
- Publish endpoint sets `publishStatus=PUBLISHED` + `publishedAt=now()` if not already published; idempotent (re-publishing is a no-op).
- Archive endpoint sets `archivedAt=now()` + `publishStatus=ARCHIVED`. Public read endpoints (slice 3) already filter to PUBLISHED only; archived rows disappear from /marketplace immediately.
- `updatedBy` must be set to the admin's User.id on every write (create + update + publish + archive). Read it from the authed request.
- `list-jobs` returns recent cover-image + audio render jobs for the story; until slices 7 and 9 ship their job tables, return an empty array. The DTO shape must be defined now so slice 7 + 9 just populate it.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- DO NOT touch the public `marketplace-stories.controller.ts` from slice 3. Add an `admin/marketplace-stories-admin.controller.ts` (or similar) in the existing admin module surface.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
