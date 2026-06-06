---
task: lola-marketplace-phaseb-slice11
spec: docs/specs/2026-05-26-marketplace-phaseb-slice11-library-entries.md
depends_on: [lola-marketplace-phaseb-slice8]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice11-library-entries.md` end-to-end. API + UI for `LibraryEntry`. "Save to library" on the marketplace story detail page actually persists. `/library` route lists the family's saved + in-progress + archived stories.

## Read first

- The spec file in full
- The parent plan section "API Surface -> Authenticated (parent)" + "Web Changes -> Library tab" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- The slice-2 `LibraryEntry` Prisma model in `apps/api/prisma/schema.prisma`
- The slice-8 `save-to-library-button.tsx` (placeholder currently toasts "Coming soon"; you'll wire it up)
- The existing parent auth pattern in `apps/api` (JwtAuthGuard or similar; mirror it for the new endpoints)
- The existing family/account context in the web app (the `useFamilyAccount` or similar hook)
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/api test` passes
- `pnpm --filter @lola/web test` passes
- `tsc --noEmit` clean across api + web
- `pnpm build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY

## HARD CONSTRAINTS

### Allowed-edit surface

- `apps/api/src/modules/library/**` (NEW module; mirror the marketplace module structure)
- `apps/api/src/app.module.ts` (wire the new LibraryModule)
- `apps/web/src/app/[locale]/library/**` (NEW route)
- `apps/web/src/app/[locale]/marketplace/[slug]/save-to-library-button.tsx` (wire the placeholder to the new API)
- `apps/web/src/lib/library-api-client.ts` (NEW client)
- `apps/web/messages/de.json` + `apps/web/messages/en.json` (additive i18n)
- `docs/specs/2026-05-26-marketplace-phaseb-slice11-library-entries.md` (status frontmatter line only)

### Forbidden surface

- `apps/api/prisma/schema.prisma` (LibraryEntry already exists from slice 2; do NOT edit the schema)
- `apps/api/src/modules/marketplace/**` (this module's surface is stable from slices 3/5/7/9; do NOT touch)
- `apps/api/src/modules/relatives/**`, `children/**`, `families/**` (out of scope)
- `apps/web/src/app/[locale]/families/**`, `apps/web/src/components/wizards/**` (out of scope)
- `apps/web/src/lib/types.ts`, `apps/web/src/lib/marketplace-catalog.ts` (do not touch)

### Other constraints

- Stay in this worktree. Do not push.
- Auth: every endpoint requires the existing parent auth guard. `familyAccountId` comes from the authed request, NEVER from the request body.
- Endpoints:
  - `POST /api/library/entries` body `{marketplaceStoryId?: string, generatedStoryId?: string}` (exactly one must be set; reject 400 otherwise). Returns the created entry. Idempotent: a duplicate (same familyAccountId + same marketplaceStoryId/generatedStoryId) returns the existing row.
  - `GET /api/library/entries` returns the family's entries grouped by status (`IN_PROGRESS`, `COMPLETED`, `ARCHIVED`).
  - `PATCH /api/library/entries/:id` body `{status: ...}` updates the status. Verify the entry belongs to the authed family (403 otherwise).
- Library tab: three sections by status. Each row shows story title, hero image, last-played timestamp (or `startedAt` when no `completedAt`), primary CTA matching the status (resume / replay / unarchive). Empty state with a CTA back to `/marketplace`.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- The marketplace story detail page (slice 8) is locale-prefixed: the "Save to library" button is in the slug subtree. The library route is similarly locale-prefixed: `apps/web/src/app/[locale]/library/`.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
