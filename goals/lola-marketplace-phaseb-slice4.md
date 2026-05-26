---
task: lola-marketplace-phaseb-slice4
spec: docs/specs/2026-05-26-marketplace-phaseb-slice4-web-marketplace-page-api.md
depends_on: [lola-marketplace-phaseb-slice3]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice4-web-marketplace-page-api.md` end-to-end. Swap the `/marketplace` web page from importing the static `apps/web/src/lib/marketplace-catalog.ts` to fetching from the public `GET /api/marketplace/stories` endpoint that slice 3 just shipped. Card click navigation changes from "open CreateStoryModal" to navigate to `/marketplace/[slug]` (route added in slice 8; this link will 404 until then, which is intentional transitional state).

## Read first

- The spec file in full
- The parent plan section "Web Changes -> /marketplace" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- `apps/web/src/app/[locale]/marketplace/` (or wherever the marketplace page actually lives; verify the App Router structure by reading the directory)
- `apps/web/src/lib/marketplace-catalog.ts` (still imported during the rollout; do NOT delete in this slice — slice 13 deletes it)
- The repo's existing pattern for client-side data fetching from the API (look for SWR or TanStack Query setup; this repo may have a shared hook)
- An existing data-driven page in `apps/web` to mirror the fetching pattern
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/web test` passes
- `pnpm --filter @lola/web tsc --noEmit` clean
- `pnpm --filter @lola/web build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(web): marketplace page reads from API`)

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- DO NOT delete `apps/web/src/lib/marketplace-catalog.ts`. It is still imported by the seed script in `apps/api/prisma/seed-marketplace.ts` (slice 2) and by the AdminStory store (still alive until slice 6). It is deleted in slice 13.
- Card click MUST navigate to `/marketplace/[slug]` even though that route 404s until slice 8 lands. Document this transitional state in the PR body (the operator will copy it).
- Preserve the existing visual grid layout, ordering hints, and locale-strict filter. The data source changes; the UX must not.
- Loading skeleton during the initial fetch. Acceptable client cache: stale-while-revalidate 5 min is fine.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- The marketplace web page is the most visible page touched by Phase B. If the test pattern in this repo requires a Playwright / e2e check, defer that to an open_thread; the unit-level visual-parity test (snapshot or DOM assertion against the seeded 13 dino stories) is the gate for this slice.
- If the existing card click triggers `AddToFamilyModal` -> `CreateStoryModal` directly, the rewire to `/marketplace/[slug]` is a behavior change. That is INTENTIONAL: slice 8 ships the new detail page; this slice is the link surface that gets us there. The bug where Create stays disabled because `selectedChildIds` is empty (per the memory `project_marketplace_user_stories`) is FIXED implicitly because the new detail page handles its own state.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
