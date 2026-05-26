---
task: lola-marketplace-phaseb-slice9
spec: docs/specs/2026-05-26-marketplace-phaseb-slice9-audio-render-pipeline.md
depends_on: [lola-marketplace-phaseb-slice5]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice9-audio-render-pipeline.md` end-to-end. Stands up the example-voice audio pre-rendering pipeline: an admin "Render audio" button enqueues per-voice renders for a marketplace story; a background worker (the existing in-process async pattern) calls ElevenLabs through the existing client, uploads each output to Storage Brain, and creates `MarketplaceAudioAsset` rows. Re-renders mark prior assets `isCurrent=false`.

## Read first

- The spec file in full
- The parent plan section "External Integrations -> ElevenLabs" and "Data Model -> MarketplaceAudioAsset"
- The existing ElevenLabs client used by `StoryPipelineV2Service` (find it; do NOT introduce a second client). It lives somewhere under `apps/api/src/modules/llm/` or `apps/api/src/modules/voice/` — verify by greping for "elevenlabs" or "ELEVENLABS_API_KEY"
- `apps/api/src/modules/marketplace/admin-marketplace.controller.ts` and `admin-marketplace.service.ts` (slice 5/6 admin surface; extend for the new endpoint)
- `apps/api/src/modules/marketplace/cover-image-jobs.ts` (slice 7's in-memory job tracker; mirror the pattern for audio jobs)
- `MEMORY.md` entry `project_admin_voice_curation_ui.md` for the premade voice list (`default-voices.ts`)
- `MEMORY.md` entry `reference_storage_brain_admin_via_agent.md` for the lola tenant config
- `MEMORY.md` entry `feedback_birefnet_parallelism_limit.md` (informational; sets the expectation that we cap concurrent renders)
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/api test` passes (with mocked ElevenLabs client + mocked Storage Brain SDK)
- `pnpm --filter @lola/web test` passes (admin UI tests with mocked API)
- `tsc --noEmit` clean across api + web
- `pnpm build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat(marketplace): example-voice audio pre-rendering pipeline`)

## HARD CONSTRAINTS (READ BEFORE TOUCHING ANY FILE)

### Allowed-edit surface

- `apps/api/src/modules/marketplace/**` (extend the existing module; new files for audio service, audio jobs tracker, etc.)
- `apps/web/src/app/admin/marketplace/**` (admin UI for the Render Audio button + per-voice status display)
- `apps/web/src/lib/admin-marketplace-api-client.ts` (extend with the new endpoints; do NOT remove existing exports)
- `apps/web/messages/de.json` + `apps/web/messages/en.json` (i18n strings, additive only)
- `docs/specs/2026-05-26-marketplace-phaseb-slice9-audio-render-pipeline.md` (status frontmatter line only)

### Forbidden surface (DO NOT EDIT OR DELETE)

- `apps/api/src/modules/llm/**`, `apps/api/src/modules/voice/**` — REUSE the existing ElevenLabs client; if you need to expose a new method, prefer wrapping at the marketplace-module level or adding a small thin export. Do NOT refactor the existing client.
- `apps/api/src/modules/relatives/**`, `apps/api/src/modules/children/**`, `apps/api/src/modules/families/**` — out of scope, do not touch
- `apps/web/src/app/[locale]/families/**`, `apps/web/src/components/wizards/**` — out of scope
- `apps/api/prisma/schema.prisma` — slice 2 already added MarketplaceAudioAsset; you should NOT need to edit the schema. If you find you need a new field, surface an open_thread and use what's already there
- `apps/web/src/lib/types.ts`, `apps/web/src/lib/marketplace-catalog.ts` — do not touch

If you think you need to edit a file outside the allowed-edit list, STOP and surface an open_thread.

### Other constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- Endpoint: `POST /api/admin/marketplace/stories/:id/render-audio` returns `{jobId, pollUrl}` IMMEDIATELY. Background processes the renders one voice at a time (sequential is fine; cap at ~3 parallel if you choose parallel per `feedback_birefnet_parallelism_limit` as a guideline for "be conservative about parallelism on this host").
- Voice selection: for v1, render the first 3 female + 2 male voices from `default-voices.ts` whose `languages` includes the story's primary language. If `default-voices.ts` doesn't have a clear list shape, surface an open_thread describing what you found and use a sensible default (e.g. all default voices).
- Storage Brain path: `marketplace/<story-slug>/audio/<voice-id>-<language>-<asset-id>.mp3` (or whatever ElevenLabs returns; verify the mime type)
- Cost tracking: persist `costUsd` from ElevenLabs response on `MarketplaceAudioAsset.costUsd`. Also persist `voiceId`, `voiceLabel`, `voiceGender`, `language`, `durationMs`.
- Re-render semantics: on a new render for the same (storyId, voiceId, language) triplet, the prior asset's `isCurrent=false` and `supersededById` points to the new asset.
- `GET /api/admin/marketplace/stories/:id/jobs` (the existing list endpoint from slice 5/7) should now include audio jobs alongside image jobs. The DTO shape was reserved for this.
- Admin UI shows per-voice render status (queued / running / succeeded / failed) and the cost.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- The audio player itself is slice 10. This slice only produces the assets.
- ElevenLabs API key: env var name is `ELEVENLABS_API_KEY` (verify by reading the existing client). Document that this must be present in Infisical /apps/api /prod and /dev (already is, since StoryPipelineV2 uses it).
- The existing ElevenLabs client may be designed for streaming audio into a final story output. For pre-rendered marketplace audio you need the full audio file as bytes. If the existing client doesn't expose a "render text to MP3 bytes" method, ADD a thin method on the existing client (smallest possible change). Do NOT fork the client.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
