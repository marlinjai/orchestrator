---
task: lola-marketplace-phaseb-slice8
spec: docs/specs/2026-05-26-marketplace-phaseb-slice8-story-detail-page.md
depends_on: [lola-marketplace-phaseb-slice6, lola-marketplace-phaseb-slice2]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice8-story-detail-page.md` end-to-end. Adds the story detail page at `apps/web/src/app/[locale]/marketplace/[slug]/` (the route slice 4 already links to but currently 404s). Server-rendered Next.js page that renders hero image, title, description, badges (age + duration), voice roles preview, and the preview text paragraphs. Audio playback placeholder only (slice 10 wires the real player).

## Read first

- The spec file in full
- The parent plan section "Web Changes -> /marketplace/[slug]" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- The existing marketplace web page from slice 4 (the API client at `apps/web/src/lib/marketplace-api-client.ts`, the `/marketplace` route layout)
- `apps/api/src/modules/marketplace/marketplace-stories.controller.ts` and DTOs (slice 3's read endpoints; the detail response shape is what feeds this page)
- The existing CreateStoryModal (the one the "Personalize for my family" CTA opens; understand its props so we can pre-fill correctly)
- The repo's App Router structure under `apps/web/src/app/[locale]/marketplace/`
- `MEMORY.md` entry `project_marketplace_user_stories` for the canonical step 3 spec
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/web test` passes
- `pnpm --filter @lola/web tsc --noEmit` clean
- `pnpm --filter @lola/web build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(web): marketplace story detail page`)

## HARD CONSTRAINTS (READ BEFORE TOUCHING ANY FILE)

A prior attempt at this slice was discarded because the Worker deleted unrelated production code (the entire relatives subsystem). DO NOT REPEAT. This slice is ONLY ABOUT THE NEW PAGE.

### Allowed-edit list

You may edit ONLY these files (or new ones inside the `apps/web/src/app/[locale]/marketplace/[slug]/` directory):

- `apps/web/src/app/[locale]/marketplace/[slug]/page.tsx` (NEW)
- `apps/web/src/app/[locale]/marketplace/[slug]/*.tsx` (NEW components scoped to the story-detail page: audio-player-placeholder, voice-role-preview, marketplace-story-cta, etc.)
- `apps/web/src/app/[locale]/marketplace/[slug]/*.test.ts` or `*.spec.ts` (NEW colocated tests)
- `apps/web/src/lib/marketplace-api-client.ts` (existing; you MAY extend it with a `getMarketplaceStoryDetail(slug, locale)` function if not already there, but do NOT remove any existing exports)
- `apps/web/messages/de.json` and `apps/web/messages/en.json` (add NEW i18n strings only; do NOT remove or rename existing ones; respect the `pnpm --filter @lola/web i18n:check` parity guard per memory `reference_messages_json_editing`)
- `docs/specs/2026-05-26-marketplace-phaseb-slice8-story-detail-page.md` (status frontmatter line only)

### Forbidden surface

DO NOT EDIT OR DELETE ANY of these areas, even if you think they relate. They are out of scope:

- `apps/api/**` ANY file. Slice 8 is web-only. Detail data comes from slice 3 endpoints already.
- `apps/web/src/app/[locale]/families/**` (family tree pages)
- `apps/web/src/components/wizards/**` (child wizard, etc.)
- `apps/web/src/lib/types.ts`
- `apps/web/src/lib/marketplace-catalog.ts` (slice 13 deletes this; slice 8 must leave it alone)
- ANY `relatives/`, `relationship-graph/`, `children/`, `family-tree/` directories
- ANY existing test file in those areas

If you think you need to edit a file outside the allowed-edit list, STOP and surface an open_thread describing what you wanted to do and why. Do not delete or refactor existing production code under any circumstances.

### Other constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- Page is server-rendered (Next.js 15 App Router, RSC). Fetches `GET /api/marketplace/stories/:slug` at request time. 404s cleanly when the story does not exist (use `notFound()` from `next/navigation`).
- Audio section: render a small placeholder component ("Example voices coming soon" or similar) named clearly so slice 10 can replace it. DO NOT add the audio player itself.
- "Personalize for my family" CTA opens the existing `CreateStoryModal` PRE-FILLED with the marketplace template + a default child preselected from the parent's family. READ the existing CreateStoryModal's props and the existing family store to derive the default child id; do NOT modify either of those upstream files. Pass everything you need via props.
- "Save to library" secondary CTA is a placeholder button that toasts "Coming soon" until slice 11 wires the LibraryEntry POST.
- Hero image: use the `heroImageUrl` from the slice-3 detail DTO. When null + `seedHeroImagePath` is present, the DTO already resolves to one canonical URL; the page consumes that one field.
- The page must respect the i18n locale. The detail page must show the story in the active locale. If the requested slug + active locale combination is not published, return 404.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- Reuse existing components where possible. Do not refactor them. If a needed prop is missing on an existing component, prefer wrapping it locally over modifying the upstream component.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
