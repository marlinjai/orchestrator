---
task: lola-marketplace-phaseb-slice2
spec: docs/specs/2026-05-26-marketplace-phaseb-slice2-prisma-models-and-seed.md
depends_on: [lola-marketplace-phaseb-slice1]
shared_state: [prisma, migrations]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice2-prisma-models-and-seed.md` end-to-end. This adds the four marketplace Prisma models (`MarketplaceStory`, `MarketplaceImageAsset`, `MarketplaceAudioAsset`, `LibraryEntry`) plus two enums to `apps/api/prisma/schema.prisma`, generates the migration, and writes an idempotent seed script that upserts the 13 existing dino stories by slug.

Also produces a one-time uploader script (callable manually, NOT auto-run on deploy) that pushes the 13 committed PNGs from `apps/web/public/marketplace/dinos/story-cards/<slug>.png` to Storage Brain via the `@marlinjai/storage-brain-sdk` and creates `MarketplaceImageAsset` rows with `provider='seed'`.

## Read first

- The spec file in full
- The parent plan section "Data Model" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md` for the four model definitions (copy verbatim, refining only what the spec calls out)
- `apps/api/prisma/schema.prisma` (current schema; you will append to it without touching existing models. Confirm the existing `FamilyAccount` and `Story` relation names so the back-relations on the new models compile)
- `apps/web/src/lib/marketplace-catalog.ts` (the source of the 13 dino-story seed data; the seed script reads this file or duplicates its contents into the seed input)
- An existing seed or migration script in this repo to mirror the style (look under `apps/api/prisma/`)
- `.claude/rules/tdd.md`
- `MEMORY.md` entry `reference_worktree_prisma_shared_db.md` if you encounter migrate-dev drift: use a dedicated per-worktree DB. For THIS slice you should be able to run `prisma migrate dev` against the current dev DB; if it complains about drift, document the workaround in the open_threads and move on.
- `MEMORY.md` entry `reference_storage_brain_admin_via_agent.md` for the lola tenant config (allowedFileTypes: null) when verifying Storage Brain will accept the uploads.

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm prisma generate` produces a clean client
- `pnpm prisma migrate dev` applies cleanly OR (if local DB shape blocks it) the migration SQL is hand-checked and `prisma migrate diff` confirms it matches the schema; document in commit message
- `pnpm --filter @lola/api test` passes
- `pnpm --filter @lola/api tsc --noEmit` clean
- `pnpm build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(api): marketplace prisma models + seed for 13 dino stories`)

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- Do NOT touch any model that already exists in `schema.prisma` other than adding the necessary back-relations on `FamilyAccount` (for `LibraryEntry`) and `Story` (for `LibraryEntry.generatedStory`). The new models are additive; the migration must be additive only.
- The Storage Brain uploader is a script (e.g. `apps/api/scripts/upload-marketplace-seed-images.ts`) callable via `pnpm exec tsx ...`. It is NOT wired into the migration or the deploy pipeline. The PR description should note that the operator runs it manually once after this PR merges.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output. Use colons, parentheses, commas, periods.
- The `seedHeroImagePath` column on `MarketplaceStory` is INTENTIONALLY transitional and gets dropped in slice 13. Keep it nullable, add a comment in the schema noting that.
- The seed script must be idempotent (upsert by slug). Re-running it on an already-seeded DB must succeed without errors and without creating duplicates.
- Tests for the seed script: at least one unit test that seeds into a mocked Prisma client and asserts 13 upserts with the correct slugs. Tests for the uploader script can be skipped at this stage (Storage Brain side effects are integration-only); document this in the spec's open_threads if you skip them.

## Notes

- The seed script reads from `apps/web/src/lib/marketplace-catalog.ts`. There is a clean way to do this: import the `MARKETPLACE_TEMPLATES` array directly (the file is in the workspace and the API can depend on the web package via the existing turborepo wiring) OR duplicate the data into the seed file. Prefer the direct import if turborepo allows it without cycles; otherwise duplicate and add an open_thread to dedupe in slice 13. Check the existing turbo dep graph first.
- After this slice lands, the operator will run the uploader script manually to populate `MarketplaceImageAsset` rows for the 13 seed PNGs, then continue with slice 3.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
