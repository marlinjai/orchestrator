---
task: studio-rehost-sync-images
shared_state: []
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Stop storing sync-generated images as full base64 data URLs in Postgres. Today the sync image path (`persistSyncResult` in `src/lib/jobs/run-generation-job.ts`, ~lines 428-453) writes the provider's base64 data URL straight into `Asset.url` with `storageFileId = null`. This is the ONE asset class not re-hosted to Storage Brain, it bloats Postgres rows (a primary plus N child candidates each carry a full data URL), and it violates the "never hot-link, always re-host" rule that 3D / video / audio already follow. Re-host new sync images to Storage Brain. This is forward-only; existing data-URL rows must keep rendering.

## Read first

- `src/lib/jobs/run-generation-job.ts` (`persistSyncResult` and the image branch; how `Asset` rows are written for the primary + child candidates, and how `messageId` / lineage are set)
- `src/lib/storage/url-mirror.ts` (`mirrorUrlToStorageBrain`: downloads an http(s) binary, 100MB cap, `contextForMime`, optional `withWorkspace`, signs 24h, returns `{ fileId, url, sizeBytes, mimeType }`)
- `src/lib/storage/glb-mirror.ts` (the thin wrapper pattern for a context-pinned mirror)
- `src/lib/asset/sign.ts` (`signAssetUrl`: re-signs when `storageFileId` present, PASSES THROUGH a persisted `url` when `storageFileId` is null; this is what keeps legacy data-URL rows rendering)
- `src/lib/jobs/handlers/complete-job.ts` (how the async path mirrors then writes `storageFileId` + signed `url` + `metadata.sourceUrl`; mirror this shape)
- `src/lib/storage.ts` / `@marlinjai/storage-brain-sdk` usage (the `getStorage()` singleton, the upload API)

## Definition of done

1. Add a data-URL-aware mirror. `mirrorUrlToStorageBrain` currently fetches an http(s) URL; a `data:` URL must be decoded to a buffer and uploaded directly. Either extend `url-mirror.ts` to detect a `data:` URL (parse mime + base64 -> Buffer -> storage upload, same signed-URL return shape) OR add a sibling `mirrorDataUrlToStorageBrain`. Prefer extending `mirrorUrlToStorageBrain` so callers stay uniform. Respect the 100MB cap (images will not hit it, but keep the guard).
2. In `persistSyncResult`'s image branch, for EACH produced image (primary + every child candidate): mirror the data URL to Storage Brain, then write the `Asset` with `storageFileId`, the signed `url`, `mimeType`, and `metadata.sourceProvider` (mirror the async path's asset shape). Do NOT also persist the raw base64 data URL into `Asset.url`.
3. Back-compat (forward-only): do NOT migrate existing rows. `signAssetUrl` already passes through a data-URL `url` when `storageFileId` is null, so old rows still render. Add a test asserting that pass-through still holds.
4. The `Message`/chat path that currently surfaces the image must keep working: confirm what the chat UI reads (the `Asset.url` after `signAssetUrl`); a freshly signed Storage Brain URL must be returned, not the data URL.
5. Failure handling, production-grade: if the mirror fails, the job must FAIL loudly with a clear error (do not silently fall back to persisting the data URL and pretend success). Surface it on the job error.
6. Tests (storage seam mocked via the existing `__setAssetSignerForTesting` / a storage mock): (a) a sync image generation writes an `Asset` with a non-null `storageFileId` and no `data:` in `url`; (b) a multi-candidate run mirrors every candidate; (c) legacy pass-through still renders; (d) a mirror error fails the job with a surfaced message.

Plus, always:
- the `verify` gate passes
- single conventional commit describing the WHY (sync images were base64-in-Postgres; now re-hosted to Storage Brain like every other modality)

## Constraints

- Do NOT touch the async (3D / video / audio) completion path; it already mirrors correctly.
- Do NOT write a one-off data migration of existing rows (out of scope; pass-through covers them). If you think a backfill is warranted, file it as an `open_thread`, do not build it.
- Keep `Project.workspaceId` out of scope (it is unpopulated today); call the mirror WITHOUT a workspace scope, matching the current async path.
- No em-dashes or en-dashes in new code/comments.
- Stay in this worktree. Do not push or merge.
- When done, output a final message that the task is complete.
