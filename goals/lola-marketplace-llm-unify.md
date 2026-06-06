---
task: lola-marketplace-llm-unify
spec: (none — implement from this goal)
---

# Goal

Trello card `6a16c211158a111aa377c49e` ("Description and story generation should work in the same way it does for the user-generated stories with the Anthropic call").

On the admin Marketplace "Add Story" form (`/admin/marketplace`, screen sections `CARD PREVIEW` / `IMAGE` / `TOPIC` / `HEADLINE` / `DESCRIPTION` / `STORY TEXT` / `TAGS` / `DURATION` / `AGES` / `VOICE ROLES`), the `DESCRIPTION` ("A short teaser shown on the marketplace card...") and `STORY TEXT` ("Full story text shown when the card is opened...") are manual textareas. The admin types both by hand.

This is inconsistent with the user-generated stories flow, which uses Anthropic via the LLM service to:
- suggest a description from title + age range (we shipped this for users in PR #154 with child names support)
- generate the full story text via the structured story pipeline (StoryPipelineV2)

Unify: the admin Add-Story form gets "Auto-generate" / "From title" buttons next to both textareas that call the SAME LLM endpoints user-facing stories use. Admin can still edit / override before saving.

## Read first

- `apps/web/src/app/admin/marketplace/` (Add-Story form UI). The screenshot showed fields TOPIC, HEADLINE, DESCRIPTION, STORY TEXT, TAGS, DURATION, AGES, VOICE ROLES. Find the form component.
- `apps/api/src/modules/stories/stories.controller.ts` + `stories.service.ts::suggestDescription` (lines around 139-179, recently extended with `childNames` per PR #154).
- `apps/api/src/modules/stories/story-pipeline-v2*` for the structured writer pipeline.
- `apps/api/src/modules/marketplace/*` for the admin marketplace endpoints (the create / update story handler).
- Memory: `project_marketplace_user_stories.md`, `project_story_pipeline.md`.

## Definition of done

Backend (apps/api):
- Expose a marketplace-admin-only LLM helper endpoint (or reuse the existing user-facing one with admin scope). Recommended: extend the existing `description-suggestion` endpoint so it accepts an admin-mode invocation that does NOT require `familyId`/`userId` ownership (admin can suggest for any story). Add an analogous `POST /admin/marketplace/stories/story-text-suggestion` (or reuse if there's already a pipeline-trigger endpoint).
- Both endpoints share the same prompts / LLM service / attribution logging the user flow uses. No prompt drift.
- AdminGuard protects the admin variants. Existing user endpoint stays unchanged for users.

Frontend (apps/web admin):
- Two buttons on the Add-Story form:
  - Next to DESCRIPTION: "Aus Titel vorschlagen" (German UI — match repo convention; the form is in German per the screenshot). Calls the description-suggestion endpoint with `{ title, ageMin, ageMax, locale }`. Fills the textarea with the response. Admin can edit.
  - Next to STORY TEXT: "Geschichte generieren". Calls the story-text endpoint with `{ title, description, ageMin, ageMax, locale, voiceRoles }`. Fills the textarea. Admin can edit.
- Both show a loading state while the LLM call is in flight. Both surface a friendly error on failure (no raw error strings).
- Disabled state: button disabled until the inputs it depends on are filled (e.g. story-text button needs description filled first).

Tests:
- Backend: unit test for the admin endpoint variants. AdminGuard test that non-admin users are rejected. Test that the prompt construction is identical between admin and user flow (factor the prompt into a shared helper if needed).
- Frontend: component test that clicking each button calls the right endpoint, handles loading + error + success.
- All existing `pnpm --filter @lola/api test` and `pnpm --filter @lola/web test` pass.

Conventional commit: `feat(admin-marketplace): LLM-powered description + story-text suggestion buttons`.

## Constraints

- Branch from `origin/main`.
- Stay in worktree, push branch + PR via gh.
- Do NOT change the user-facing `description-suggestion` behaviour (PR #154 just shipped it). Only ADD an admin variant or admin-mode flag.
- Do NOT introduce a new LLM provider or model selection. Reuse what user-generated stories use.

## Notes

- Reference screenshot: `/tmp/feedback-shots/description-marketplace.png` (main session only).
- The card explicitly says "in the same way it does for the user-generated stories with the Anthropic call". Means: same Anthropic model, same prompt construction, same LLM service abstraction. No bespoke admin pipeline.
- If you find that the marketplace catalog persistence is now in `@lola/types` workspace package (per recent memory `project_post_voice_cast_followups.md`), make sure the endpoint contract types live there too.
- Final message: branch, PR URL, count of new tests, list of endpoints added/extended.
