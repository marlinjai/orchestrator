---
task: lola-marketplace-phaseb-slice3
spec: docs/specs/2026-05-26-marketplace-phaseb-slice3-public-read-endpoints.md
depends_on: [lola-marketplace-phaseb-slice2]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice3-public-read-endpoints.md` end-to-end. Adds the public marketplace read endpoints (`GET /api/marketplace/stories` with category + language filters, `GET /api/marketplace/stories/:slug`) backed by the Prisma models that slice 2 just shipped. Only `PUBLISHED` rows are returned. Stable sort: `displayOrder ASC, publishedAt DESC`.

## Read first

- The spec file in full
- The parent plan section "API Surface -> Public" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- `apps/api/prisma/schema.prisma` (current schema, including the four marketplace models added in slice 2)
- An existing NestJS module in this repo with a public-read controller to mirror the pattern (look for endpoints without auth guards, e.g. landing page consumers or the open `/api/v1/demo/generate` route)
- `apps/api/src/modules/lumitra-studio/lumitra-studio.module.ts` (the slice-1 module is a good shape reference, though it has a different auth posture)
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/api test` passes (must include integration tests against a test DB if the spec calls for them)
- `pnpm --filter @lola/api tsc --noEmit` clean
- `pnpm build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(api): public marketplace read endpoints`)

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- Public endpoints MUST NOT require auth. Confirm they bypass any global guards (this repo may have a global auth guard with `@Public()` opt-out; verify the pattern by reading similar endpoints).
- Public list endpoint must return ONLY `PUBLISHED` rows. Draft and archived rows MUST NOT leak.
- `language` filter is strict: a story whose `languages: string[]` does NOT include the requested locale must be excluded. Default behavior when the filter is omitted: return all published rows regardless of language (the client filters client-side, matching today's static behavior).
- DTOs must include the hero image URL (resolved via `heroImageAssetId` -> `MarketplaceImageAsset.storageBrainUrl`). When `heroImageAssetId` is null but `seedHeroImagePath` is set (transitional column from slice 2), return the seed path as the URL. The frontend treats both as same-shaped URL strings.
- DO NOT include audio assets in the detail response yet (slice 9 ships audio). The DTO field for audio should be an empty array, typed but empty, so slice 10 can wire it up without DTO churn.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output. Use colons, parentheses, commas, periods.

## Notes

- Integration tests likely need the same per-worktree DB pattern slice 2 used. Reuse `lola_slice2`'s DB or create `lola_slice3`. Either way, document in open_threads.
- If the seed script from slice 2 hasn't been run against the worktree DB yet, this slice can run it as part of test setup. The seed is idempotent.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
