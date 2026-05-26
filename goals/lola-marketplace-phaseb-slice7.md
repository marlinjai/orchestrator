---
task: lola-marketplace-phaseb-slice7
spec: docs/specs/2026-05-26-marketplace-phaseb-slice7-cover-image-generation.md
depends_on: [lola-marketplace-phaseb-slice6]
---

# Goal

Implement the leaf spec at `docs/specs/2026-05-26-marketplace-phaseb-slice7-cover-image-generation.md` end-to-end. Wires the Lumitra Studio client (slice 1) into the admin marketplace flow so an admin can click "Generate cover image" on a marketplace story, the API kicks off a Studio job, the result PNG persists to Storage Brain via `@marlinjai/storage-brain-sdk`, a `MarketplaceImageAsset` row is created, and on admin confirm becomes the story's hero (`heroImageAssetId`).

## Read first

- The spec file in full
- The parent plan section "External Integrations -> Lumitra Studio" + "External Integrations -> Storage Brain" + "Web Changes -> /admin/marketplace" in `docs/plans/2026-05-26-marketplace-cms-phase-b.md`
- `apps/api/src/modules/lumitra-studio/lumitra-studio.service.ts` (slice 1; reuse `generateImage()`)
- `apps/api/src/modules/marketplace/admin-marketplace.service.ts` and `admin-marketplace.controller.ts` (slice 5 + 6 admin surface; extend, don't fork)
- `apps/web/src/app/admin/marketplace/story-form.tsx` (slice 6 admin form; you'll add the button + preview here)
- `MEMORY.md` entry `reference_storage_brain_admin_via_agent.md` for the lola tenant config (`allowedFileTypes: null`) and the SDK usage pattern
- `apps/api/prisma/upload-marketplace-seed-images.ts` (slice 2 uploader; mirror the Storage Brain SDK usage pattern)
- `.claude/rules/tdd.md`

## Definition of done

Whatever the spec's Definition of done lists. Plus, always:

- `pnpm --filter @lola/api test` passes (with mocked `LumitraStudioService` + mocked Storage Brain SDK)
- `pnpm --filter @lola/web test` passes (admin UI tests with mocked API)
- `tsc --noEmit` clean across api + web
- `pnpm build` clean
- Spec frontmatter `status: draft` becomes `status: done` in the same commit
- Single commit on this branch with a conventional-commit message describing the WHY (e.g. `feat: admin cover-image generation via Lumitra Studio + Storage Brain`)

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote. The operator will handle push + PR + merge.
- The cover-image endpoint is `POST /api/admin/marketplace/stories/:id/cover-image`. Returns `{jobId, pollUrl}` IMMEDIATELY (do not block 30-60s on the HTTP connection). Background async kicks off in-process; admin UI polls a status endpoint (reuse `/api/admin/marketplace/stories/:id/jobs` from slice 5 — the DTO shape is already defined; populate it).
- Storage Brain path: `marketplace/<story-slug>/cover/<asset-id>.png`. Use the existing `@marlinjai/storage-brain-sdk` client; the lola tenant is already provisioned.
- Cost tracking: persist `costUsd` on `MarketplaceImageAsset` from the value the Lumitra Studio service returns. Persist `model` and `provider` too.
- "Use this cover" (admin confirm) is a separate API call that patches `heroImageAssetId`. The generation alone does NOT auto-set the hero — the admin reviews + chooses.
- "Discard" is a delete on the `MarketplaceImageAsset` row (or a soft-delete with a flag — verify which the model supports; the schema is from slice 2). Discarded assets MUST NOT remain as a hero candidate in the admin UI.
- Background processing: use whichever in-process async pattern this repo already has (the slice-1 LumitraStudioService uses an awaitable returning shape; the endpoint can spawn the work via `setImmediate(...)` or a fire-and-forget Promise + catch; verify by reading existing async-job code in `apps/api`). DO NOT introduce a new queue dependency.
- Admin UI: button next to the hero image field. Shows a spinner with the ~30-60s estimate. On completion, side-by-side "Use this cover" / "Discard" choice. Choosing "Use this cover" patches heroImageAssetId; choosing "Discard" deletes the asset.
- The two consumer-side env vars `LUMITRA_STUDIO_BASE_URL` + `LUMITRA_STUDIO_SERVICE_TOKEN` (added in slice 1) need to be present in Infisical `/apps/api` /prod and /dev BEFORE this endpoint works. This is operational; document it in the PR body, do not attempt to add them yourself.
- No em-dashes (U+2014) or en-dashes (U+2013) in any output.

## Notes

- The KIE/Nano Banana 2 default model on Studio is `kie/nano-banana-2`, ~$0.04/image, 30-60s round trip. The Studio brand `lola-stories` + mode `illustration` (3:4) is the default for marketplace covers. The admin UI may optionally let the admin override `brandMode` (e.g. `character` 1:1 for character covers); make it a select if the spec calls for it, otherwise hard-code to `illustration`.
- When done, output a final message that the task is complete and the spec frontmatter status has been flipped to `done`.
