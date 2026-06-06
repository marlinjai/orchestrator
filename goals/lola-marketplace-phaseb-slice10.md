---
task: lola-marketplace-phaseb-slice10
spec: docs/specs/2026-05-26-marketplace-phaseb-slice10-story-detail-audio-player.md
depends_on: [lola-marketplace-phaseb-slice8, lola-marketplace-phaseb-slice9]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice10-story-detail-audio-player.md` end-to-end. Replaces slice 8's `audio-player-placeholder` on `/marketplace/[slug]` with the real HTML5 audio player + voice switcher dropdown. Defaults to the narrator-candidate voice; streams the Storage Brain URL from the slice-3 detail DTO (audio array populated by slice 9 renders).

## Read first

- The spec file in full
- The parent plan section "Web Changes -> /marketplace/[slug]" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- The slice 8 page at `apps/web/src/app/[locale]/marketplace/[slug]/page.tsx` and `audio-player-placeholder.tsx` (the placeholder you're replacing)
- The slice 3 detail DTO (`MarketplaceStoryDetail` in `apps/api/src/modules/marketplace/dto/`) for the audio asset shape exposed on the response
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/web test` passes
- `pnpm --filter @lola/web tsc --noEmit` clean
- `pnpm --filter @lola/web build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY

## HARD CONSTRAINTS

### Allowed-edit surface

- `apps/web/src/app/[locale]/marketplace/[slug]/**` (the story detail page + new audio player component + tests)
- `apps/web/messages/de.json` + `apps/web/messages/en.json` (additive i18n)
- `docs/specs/2026-05-26-marketplace-phaseb-slice10-story-detail-audio-player.md` (status frontmatter line only)

### Forbidden surface

- `apps/api/**` (slice 10 is web-only; audio assets already exposed by slice 3 detail DTO)
- `apps/web/src/app/[locale]/families/**`, `apps/web/src/components/wizards/**`, `apps/web/src/lib/types.ts`, `apps/web/src/lib/marketplace-catalog.ts`
- ANY `relatives/`, `relationship-graph/`, `children/`, `family-tree/` directories
- ANY existing test outside the slug directory

### Other constraints

- Stay in this worktree. Do not push.
- Player uses HTML5 `<audio>` element. Streams the Storage Brain URL directly. No new dependencies (no Howler.js etc.).
- Voice switcher: select dropdown listing available example voices for the active language. Voice label + gender + duration shown.
- Default selection: the voice whose role matches the story's primary narrator role (the `voiceRoles` array; the first role with id "narrator" or similar). If no narrator role exists, default to the first voice in the list.
- Empty audio array (story has no renders yet): keep the placeholder copy, render gracefully.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- Replace `audio-player-placeholder.tsx` with a real `audio-player.tsx` (or rename it). Delete the placeholder file if you rename.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
