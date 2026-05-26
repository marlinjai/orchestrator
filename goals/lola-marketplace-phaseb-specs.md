---
task: lola-marketplace-phaseb-specs
spec: docs/plans/2026-05-26-marketplace-cms-phase-b.md
shared_state: []
---

# Goal

Read the Phase B plan at `docs/plans/2026-05-26-marketplace-cms-phase-b.md` (the source of truth for what's being built). Produce 13 per-slice spec files in `docs/specs/`, one per slice, each tightly scoped so an implementation Worker can land it in a single PR with TDD. Single commit on this branch.

## Read first

- `docs/plans/2026-05-26-marketplace-cms-phase-b.md` (the full Phase B plan; 13 slices defined in the "Slice Breakdown (for orchestrator dispatch)" section)
- `docs/plans/2026-05-22-family-tree-phase-1a-plan.md` (an example of an in-house plan + spec format already accepted in this repo, useful for the prose style and the "File Structure" table convention)
- `.claude/rules/tdd.md` (TDD rule the implementation Workers must follow; specs MUST list the co-located `.spec.ts` files that need to exist)
- `apps/api/prisma/schema.prisma` (current Prisma schema; the four new models in the plan must reference existing models like `FamilyAccount` and `Story` with the correct relation names)
- `apps/web/src/lib/marketplace-catalog.ts` (the static catalog being replaced; slice 2's seed script must derive from this file exactly)
- `apps/web/src/app/admin/marketplace/` (the localStorage-backed admin pages being rewired; slices 5 and 6 must enumerate the actual files to touch)

## Definition of done

For each of the 13 slices in the plan, produce one spec file at `docs/specs/2026-05-26-marketplace-phaseb-sliceN-<slug>.md` where N is 1..13 and `<slug>` is the slice's short identifier. Suggested slugs:

1. `lumitra-studio-client`
2. `prisma-models-and-seed`
3. `public-read-endpoints`
4. `web-marketplace-page-api`
5. `admin-crud-endpoints`
6. `admin-ui-api-rewire`
7. `cover-image-generation`
8. `story-detail-page`
9. `audio-render-pipeline`
10. `story-detail-audio-player`
11. `library-entries`
12. `voice-role-assignment-ui`
13. `cleanup-legacy-catalog`

### Required spec structure

Each spec MUST have:

```markdown
---
title: <human-readable title>
type: plan
status: draft
date: 2026-05-26
summary: <one-sentence summary>
tags: [marketplace, ...]
projects: [lola-stories]
parent_plan: docs/plans/2026-05-26-marketplace-cms-phase-b.md
slice: <N>
---

# <title>

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this spec. Co-located `.spec.ts` files are mandatory per `.claude/rules/tdd.md`. Red-Green-Refactor.

**Parent plan:** [`docs/plans/2026-05-26-marketplace-cms-phase-b.md`](../plans/2026-05-26-marketplace-cms-phase-b.md)

**Goal:** <one paragraph: what this slice accomplishes and why this slice exists as its own unit>

**Tech stack:** <whatever subset of the parent plan's stack this slice actually touches>

## File Structure

| File | Responsibility |
|------|----------------|
| `apps/api/src/...` | ... |

## Implementation

Step-by-step list (checkboxes) of work, in dependency order. Each step is small enough to land in a Red-Green-Refactor cycle.

## API surface (if applicable)

Exact endpoint shapes, request / response DTOs, status codes, auth requirements. Use TypeScript pseudo-types where helpful.

## Data model (if applicable)

Prisma model definitions copied verbatim from the parent plan, with any per-slice refinements. Migration filename convention: `prisma/migrations/<timestamp>_<slug>/`.

## Test plan

For each new service / controller / guard / strategy / filter / decorator: list the co-located `.spec.ts` file and the behaviors to assert.

## Definition of done

- [ ] <every observable outcome a reviewer would check>
- [ ] All co-located `.spec.ts` tests green
- [ ] `pnpm build` passes
- [ ] `pnpm --filter @lola/api tsc --noEmit` clean (if API surface changed)
- [ ] Single PR, conventional-commit message describing the WHY

## Out of scope

Explicit list. Anything tempting to bundle that belongs in a later slice goes here.

## Dependencies

Slices this depends on having merged. Slices that depend on this one.
```

### Per-slice content notes (must be honored)

- **Slice 1 (lumitra-studio-client)**: env vars `LUMITRA_STUDIO_BASE_URL` and `LUMITRA_STUDIO_SERVICE_TOKEN` (the prefix is correct on the consumer side per the plan's architecture decision). New module `apps/api/src/modules/lumitra-studio/`. `LumitraStudioService.generateImage({brandSlug, brandMode, prompt, aspectRatio, model?})` returns `{dataUrl, costUsd, model, provider}`. Polls /api/v1/jobs/:id for up to 6 minutes (KIE has a 5-min internal poll). Add to Infisical /apps/api /prod is OPERATIONAL not in-code; mention it in the spec but don't try to do it in the implementation.
- **Slice 2 (prisma-models-and-seed)**: copies the four models + two enums verbatim from the parent plan's `Data Model` section. The seed script is at `apps/api/prisma/seed-marketplace.ts`, idempotent upserts by slug. Also: a one-time uploader script (NOT auto-run on deploy) that pushes the 13 committed PNGs from `apps/web/public/marketplace/dinos/story-cards/<slug>.png` to Storage Brain via `@marlinjai/storage-brain-sdk` and creates `MarketplaceImageAsset` rows with `provider='seed'`. Transitional `seedHeroImagePath` column on `MarketplaceStory` documented as removed in slice 13.
- **Slice 3 (public-read-endpoints)**: GET /api/marketplace/stories returns only `PUBLISHED` rows. Stable sort `displayOrder ASC, publishedAt DESC`. Strict-filters by language. Detail endpoint includes voice roles + preview text + hero image URL + current audio assets (slice 9 populates audio; until then the array is empty).
- **Slice 4 (web-marketplace-page-api)**: The web page on Next.js 15 App Router. Card click points to `/marketplace/[slug]` even though that route is added in slice 8; until then the link will 404. That's acceptable temporary state.
- **Slice 5 (admin-crud-endpoints)**: All endpoints require the existing admin auth guard. `marlin@lolastories.com` per memory `user_admin_email`. Hard DELETE only allowed when no LibraryEntry references the story; otherwise 409 with instruction to archive.
- **Slice 6 (admin-ui-api-rewire)**: Delete `apps/web/src/app/admin/marketplace/marketplace-admin-store.ts` (localStorage code). Form posts via SWR mutation or TanStack Query (whichever the repo already uses for admin forms — verify by reading the current admin code). Optimistic update + toast.
- **Slice 7 (cover-image-generation)**: Endpoint `POST /api/admin/marketplace/stories/:id/cover-image`. Returns `{jobId, pollUrl}` immediately. Background async (no new queue; existing pattern). On success uploads to Storage Brain path `marketplace/<story-slug>/cover/<asset-id>.png`, creates MarketplaceImageAsset, patches heroImageAssetId. Admin UI shows spinner with ~30-60s estimate.
- **Slice 8 (story-detail-page)**: New route `apps/web/src/app/marketplace/[slug]/page.tsx`. Server component, fetches at request time. Render: hero image, title, description, badges (age, duration), voice roles preview, preview text paragraphs. CTA: "Personalize for my family" opens the existing CreateStoryModal pre-filled with the template + child preselected (FIXES the v0 UX bug where Create stayed disabled because `selectedChildIds` was empty — call this out in the spec).
- **Slice 9 (audio-render-pipeline)**: Use whichever background-queue pattern already exists in `apps/api` (likely `@nestjs/bullmq` or `pg-boss`). Verify by grepping for existing queue/worker code. Render via existing ElevenLabs client (the one feeding `StoryPipelineV2Service`). For v1: render 3 female + 2 male premade voices that support the story's language (read voices from `default-voices.ts`). Mark predecessors `isCurrent=false` on re-render.
- **Slice 10 (story-detail-audio-player)**: HTML5 audio element + voice picker dropdown. Default to the voice with role matching the story's primary narrator role. Stream from Storage Brain URL.
- **Slice 11 (library-entries)**: POST /api/library/entries from authed parent. GET groups by status. /library route with three sections.
- **Slice 12 (voice-role-assignment-ui)**: NEW step in CreateStoryModal when opened from the marketplace path. Map each role from the story to a FamilyMembership from the parent's family. Persist as input to existing StoryPipelineV2.
- **Slice 13 (cleanup-legacy-catalog)**: Delete `apps/web/src/lib/marketplace-catalog.ts`. Delete `seedHeroImagePath` column (NEW migration). Update memory file pointers in `MEMORY.md` for `project_marketplace_user_stories` and `project_marketplace_dino_assets` (the files themselves still exist; just update the descriptions to reflect that v0/Phase B has landed).

## Constraints

- Stay in this worktree. Do not modify files outside `docs/specs/`.
- Do not push to any remote. The operator will handle push + PR + merge.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output. Use colons, parentheses, commas, periods.
- Single commit on this branch with message `docs(specs): marketplace Phase B per-slice specs`.
- The specs are scaffolds for downstream implementation Workers; they should be DETAILED enough to drive a one-PR implementation, but they MUST NOT duplicate the entire plan. Each spec links back to the plan for the architectural context and only specifies its own slice's surface.

## Notes

- The plan is intentionally comprehensive about cross-cutting concerns (architecture decisions, integration constraints, etc.). Specs should reference it by section ("See parent plan section X for ...") rather than re-stating.
- If a slice's File Structure table can't be completed without reading more of the codebase, list "TBD by Worker on first read" with a one-line rationale. Better that than a fabricated path.
- When the spec frontmatter `slice: <N>` is set, it becomes a stable cross-reference for the orchestrator dispatch chain.
