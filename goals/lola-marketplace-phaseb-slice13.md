---
task: lola-marketplace-phaseb-slice13
spec: docs/specs/2026-05-26-marketplace-phaseb-slice13-cleanup-legacy-catalog.md
depends_on: [lola-marketplace-phaseb-slice11, lola-marketplace-phaseb-slice12]
shared_state: [prisma, migrations]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice13-cleanup-legacy-catalog.md` end-to-end. Final cleanup slice that removes the transitional surface Phase B leaves behind:

1. Delete `apps/web/src/lib/marketplace-catalog.ts` and every import of it
2. Drop the transitional `seedHeroImagePath` column from `MarketplaceStory` with a new additive Prisma migration
3. Update one-line descriptions in `MEMORY.md` (and only the descriptions; the underlying memory files stay) for the marketplace project entries to reflect that Phase B has landed

## Read first

- The spec file in full
- The parent plan section "Slice Breakdown -> Slice 13: Cleanup" + "Migration Strategy" item 5 in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- `apps/web/src/lib/marketplace-catalog.ts` (file being deleted)
- `apps/api/prisma/marketplace-seed-data.ts` (the canonical replacement; created during the seed-fix PR #148)
- `apps/api/prisma/schema.prisma` (the `MarketplaceStory.seedHeroImagePath` column being dropped)
- Grep the repo for any remaining imports of `marketplace-catalog`:
  ```sh
  grep -rn "marketplace-catalog" apps packages docs
  ```
  Every match must either be deleted, rewritten to import from the api seed data, or (for docs/specs) updated to reference the new shape.
- `MEMORY.md` (at `/Users/marlinjai/.claude/projects/-Users-marlinjai-software-dev-lola-stories/memory/MEMORY.md`)
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/api test` passes (no orphan imports)
- `pnpm --filter @lola/web test` passes
- `pnpm --filter @lola/api tsc --noEmit` clean
- `pnpm --filter @lola/web tsc --noEmit` clean
- `pnpm build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `chore(marketplace): delete legacy static catalog + drop seedHeroImagePath`)

## HARD CONSTRAINTS

### Allowed-edit / delete surface

- DELETE `apps/web/src/lib/marketplace-catalog.ts` (the whole file)
- Edit any file that imports from `marketplace-catalog` to remove or rewrite the import
- Edit `apps/api/prisma/schema.prisma` to drop the `seedHeroImagePath` column (additive migration only: `prisma migrate dev --name drop_marketplace_seed_hero_image_path` produces the SQL)
- Edit `apps/api/prisma/marketplace-seed-data.ts` to remove the `heroImage` field from each template if helpful, OR keep it (the seed no longer writes `seedHeroImagePath`; either is fine, but be consistent)
- Edit `apps/api/prisma/seed-marketplace.ts` to stop writing `seedHeroImagePath` (the field no longer exists in the schema)
- Edit `apps/api/src/modules/marketplace/marketplace-stories.service.ts` and any DTO that resolves `seedHeroImagePath` -> heroImageUrl: switch to returning null when `heroImageAsset` is unset, since the transitional fallback is gone (the operator will run the uploader script separately to populate real hero images, OR generate them via the admin UI; until then stories return null heroImageUrl)
- Edit `MEMORY.md` (at the path noted in Read first) to update the one-line descriptions for the marketplace project memories
- `docs/specs/2026-05-26-marketplace-phaseb-slice13-cleanup-legacy-catalog.md` (status frontmatter line only)

### Forbidden surface

- DO NOT touch any other Prisma model. The migration is ONLY about dropping `seedHeroImagePath`.
- DO NOT modify `apps/api/src/modules/relatives/**`, `children/**`, `families/**`, `wizards/**`
- DO NOT touch `apps/api/src/modules/library/**` or `apps/api/src/modules/lumitra-studio/**`
- DO NOT touch any slice 1-12 PR boundary unnecessarily

### Other constraints

- Stay in this worktree. Do not push.
- The migration must be SAFE for prod data. If any seeded row still has `seedHeroImagePath` populated and no `heroImageAssetId`, that story's hero will become null on the API response after this migration. That is acceptable: the operator runs the uploader script or generates covers via the admin UI to populate real hero images. Document this in the PR body.
- After this slice lands and redeploys, the seed continues to run idempotently. It no longer writes `seedHeroImagePath` (the column is gone). It still creates the 13 rows with their voice roles, preview text, etc.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- The seed script (slice 2 + fixed in PR #148) is now the canonical source for the 13 rows. The web catalog file was only kept for compatibility during phases 4-12.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
