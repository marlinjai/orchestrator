---
task: lola-marketplace-phaseb-slice12
spec: docs/specs/2026-05-26-marketplace-phaseb-slice12-voice-role-assignment-ui.md
depends_on: [lola-marketplace-phaseb-slice8]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice12-voice-role-assignment-ui.md` end-to-end. Adds a step in the `CreateStoryModal` flow (when opened from the marketplace path) that maps each voice role from the marketplace story to a family member, before generation. The assignment is persisted as input to the existing `StoryPipelineV2`.

## Read first

- The spec file in full
- The parent plan section "Web Changes -> /marketplace/[slug]" + "Marketplace user journey step 4 (Voice-Role Assignment)" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- The slice-8 marketplace-story-cta at `apps/web/src/app/[locale]/marketplace/[slug]/marketplace-story-cta.tsx` (the trigger that opens CreateStoryModal)
- The existing `CreateStoryModal` (find it; do NOT refactor — wrap or extend via props)
- `apps/api/src/modules/marketplace/marketplace-stories.service.ts` (slice 3) and the detail DTO — `voiceRoles` is a Json field on `MarketplaceStory` that contains an array of role descriptors `{id, label, description}`
- The existing voice-cast resolution path that StoryPipelineV2 takes (look in `apps/api/src/modules/llm/story-pipeline-v2.service.ts`)
- `MEMORY.md` entry `project_marketplace_user_stories` step 4 for the canonical UX
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

- `apps/web/src/app/[locale]/marketplace/[slug]/marketplace-story-cta.tsx` (the trigger; extend with voice-role assignment state)
- NEW components inside `apps/web/src/app/[locale]/marketplace/[slug]/` (e.g. voice-role-assignment-step.tsx)
- `apps/web/src/components/create-story/**` ONLY if you absolutely need to add a small new prop to CreateStoryModal to accept the role -> family-member map. Prefer wrapping at the marketplace CTA level if possible. NO refactor of CreateStoryModal internals.
- `apps/web/messages/de.json` + `apps/web/messages/en.json` (additive i18n)
- `docs/specs/2026-05-26-marketplace-phaseb-slice12-voice-role-assignment-ui.md` (status frontmatter line only)

### Forbidden surface

- `apps/api/**` ANY file (this slice is web-only; the existing pipeline already accepts the cast as input)
- `apps/api/src/modules/llm/**` (StoryPipelineV2 service stays untouched)
- `apps/api/src/modules/voice/**`, `relatives/**`, `children/**`, `families/**` (out of scope)
- `apps/web/src/app/[locale]/families/**`, `apps/web/src/components/wizards/**`
- `apps/web/src/lib/types.ts`, `apps/web/src/lib/marketplace-catalog.ts`
- `apps/web/src/app/[locale]/marketplace/[slug]/example-voice-player.tsx` and other slice-10 files (no changes needed)
- ANY `relatives/`, `relationship-graph/`, `children/`, `family-tree/` directories

### Other constraints

- Stay in this worktree. Do not push.
- The voice-role assignment step happens AFTER the user clicks "Personalize for my family" but BEFORE the existing CreateStoryModal generation step. Visually it's either an additional step inside the modal OR a small intermediate dialog. The spec dictates the shape.
- For each `voiceRole` in the marketplace story, the user picks a `FamilyMembership` (from the parent's family). Roles with `id: 'narrator'` may default to the parent (admin) themselves; other roles default to nothing assigned until the user picks. Validation: every required role must be assigned before proceeding.
- The assignment is just a TypeScript object passed to the existing CreateStoryModal as an optional prop (e.g. `voiceCast?: Record<roleId, familyMembershipId>`). The downstream StoryPipelineV2 already accepts a cast input; this slice only wires the UI side.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- This slice does NOT change generation semantics. The existing pipeline runs the story; the only difference is that the cast map is provided upfront from the marketplace UI rather than auto-resolved by the LLM mid-flight.
- If you find that CreateStoryModal does NOT currently accept a `voiceCast` prop, ADD ONE — but as a minimal prop, with a sensible default that preserves today's behavior when omitted. Do not refactor anything else in CreateStoryModal.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
