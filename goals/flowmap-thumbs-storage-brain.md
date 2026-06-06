---
task: flowmap-thumbs-storage-brain
spec: docs/plans/2026-05-31-flowmap-next-phases-handover.md (Slice A)
shared_state: [prisma, migrations, lockfile]
---

# Goal

Implement Slice A of the flowmap-next handover: move `/admin/flow` node thumbnails OUT of the committed `apps/web/public/flowmap-thumbs/*` + `flowmap.json` and INTO Storage Brain, refreshed two ways: (1) live, in-browser, from the click-to-live device-frame panel (Marlin's "capture and leave it" idea), and (2) authoritatively by the existing Playwright capture script (adapted to upload instead of write-to-disk). The committed `flowmap.json` becomes purely structural (no `preview.thumbnail`). This is the lead workstream; it makes the later drift gate (Slice B) trivially clean and fixes thumbnail staleness.

The `@lola/flowmap` package (and its `./react` canvas) MUST stay app-agnostic so a future `@lumitra/flowmap` and the generalist phase can reuse it. All lola-specific wiring (admin upload endpoint, Storage Brain client, seed-user auth, the resolve URL) lives in `apps/web` / `apps/api`, NEVER in the package.

## Read first

- `apps/api/src/modules/marketplace/cover-image.service.ts` and `apps/api/src/modules/storage/storage.service.ts`: the proven Storage Brain upload pattern (SDK `@marlinjai/storage-brain-sdk`, auth via `STORAGE_BRAIN_API_KEY`, `client.upload(file, { context, tags })`).
- `apps/api/src/modules/storage/resolve-permanent-url.ts`: ALWAYS resolve the permanent url with this helper. Storing the relative url Storage Brain returns is the known broken-thumbnail bug. Never store the relative url.
- `apps/api/src/modules/admin/admin.controller.ts` (and the existing `JwtAuthGuard` + admin guard usage): mirror that guard pattern for the new admin-only endpoint.
- `apps/api/prisma/schema.prisma`: the model conventions; you will add one small model + a migration.
- `packages/flowmap/src/react/screen-node.tsx` (the `LivePanel` and `ScreenNode`) and `packages/flowmap/src/react/flow-canvas.tsx` (or wherever `<FlowCanvas>` lives): where thumbnails render and where the live iframe loads.
- `apps/web/scripts/capture-flowmap-shots.ts` (`flowmap:shots`) and `apps/web/scripts/generate-flowmap.ts` (`flowmap:gen`): the capture + generate scripts you will adapt.
- `apps/web/src/app/admin/flow/*`: how the web app mounts the canvas; where you wire the injected props.
- `apps/web/next.config.ts`: `images.remotePatterns` (the Storage Brain host `api.storage-brain.lumitra.co` should already be present for marketplace).
- `.claude/rules/tdd.md` if present: Red-Green-Refactor, co-located `.spec.ts`, mocked `PrismaService`.

## Scope and changes

### A1. Storage Brain write path (apps/api)

New admin-only endpoint (reuse `JwtAuthGuard` + the existing admin guard), under the locale-free `/api/v1/admin` surface:

```
POST /api/v1/admin/flowmap/node-thumbnails/:nodeId   (WebP body: multipart or octet-stream)
GET  /api/v1/admin/flowmap/node-thumbnails/:nodeId    -> { url } | 404
```

- POST: build a `File` named `flowmap-thumbnail-${slug(nodeId)}.webp` where `slug = nodeId.replace(/[^a-z0-9]+/gi,'-').replace(/^-+|-+$/g,'').toLowerCase()` (same slug the capture script uses). Upload with `context: 'flowmap-thumbnail'` (flat string, NO `/`) and `tags: { nodeId, source }`. Resolve the PERMANENT url via `resolve-permanent-url.ts`. Persist + return `{ url }`. `source` tag is `'live'` or `'playwright'`.
- GET: look up the latest thumbnail for that `nodeId` and return its permanent url, or 404.
- Persistence: add a small `FlowmapThumbnail` Prisma model (`nodeId` unique, `fileId`, `url`, `source`, `updatedAt`) + a migration. This is clearer than relying on a Storage-Brain tag lookup. Wire it through a tiny service.

### A2. Live in-browser capture (apps/web + a generic package prop)

- The `LivePanel` loads a SAME-ORIGIN iframe at `node.preview.live`, so `iframe.contentDocument.body` is reachable.
- Add `html-to-image` (actively maintained; not yet a dep) to `apps/web` ONLY. The package stays generic: `LivePanel` / `FlowCanvas` gain an OPTIONAL `onCaptureThumbnail?(nodeId: string, blob: Blob): Promise<void>` prop. The capture button calls `htmlToImage.toBlob(iframe.contentDocument.body)` then `onCaptureThumbnail(nodeId, blob)`. The package never imports `html-to-image` itself if that would couple it; if the capture call must live in the package, guard it so the package has no app-specific URL. Prefer: the web app passes a capture handler; the package just exposes the button + calls the prop.
- `apps/web` provides `onCaptureThumbnail` that POSTs the blob to the A1 endpoint. Add an "Update thumbnail" button in the live panel header (next to the device toggle). Optionally auto-capture once on open after a short settle.
- Document the fidelity caveat in a UI tooltip/comment: in-browser capture is lower fidelity than Playwright (fonts/shadows/canvas/webgl/3D may render imperfectly). Capture at Desktop device size. This is the OPPORTUNISTIC path; Playwright (A3) stays authoritative.

### A3. Authoritative capture (adapt the existing script)

- Adapt `apps/web/scripts/capture-flowmap-shots.ts`: instead of writing `public/flowmap-thumbs/<slug>.webp` and patching `flowmap.json`, upload the `sharp`-produced WebP buffer to the A1 endpoint with `source: 'playwright'`. KEEP the login-as-seed-admin flow, the "wait out Loading" settle, and the dev-only host guard.
- Do NOT try to run this against a live deploy inside this task (it needs a running web+api + SEED_USER creds via Infisical). Adapt the script + document, in the script header and/or a short note in the PR, BOTH options: (a) run it manually wrapped in Infisical `--path=/apps/api` for `SEED_USER_EMAIL`/`SEED_USER_PASSWORD` against the dev origin, and (b) a CI job after the web deploy against the deployed origin with a CI seed-admin token. Adding the actual CI job can be a follow-up `open_thread`; do not block on it.

### A4. Canvas fetch-by-key + remove committed thumbnails

- `<FlowCanvas>` / `ScreenNode`: render the thumbnail from an injected `resolveThumbnailUrl?(nodeId: string): string | Promise<string>` prop instead of `node.preview.thumbnail`. Lazy-load the image; on 404 / missing, fall back gracefully to the existing label card.
- `apps/web` wires `resolveThumbnailUrl` to the A1 GET endpoint (or a deterministic Storage-Brain url by key).
- Delete `apps/web/public/flowmap-thumbs/*` (the ~33 committed webp). Stop writing `preview.thumbnail` in `generate-flowmap.ts` (drop the `preserveThumbnails` path). `flowmap.json` becomes purely structural. Regenerate it (`pnpm --filter @lola/web flowmap:gen`) and commit the now-structural file.
- Confirm the Storage Brain host is in `apps/web/next.config.ts` `images.remotePatterns` if you render via `next/image`.

## Definition of done

- `pnpm --filter @lola/api test` passes (jest; mock `PrismaService` and `fetch`/SDK in unit tests, no live DB in tests).
- `pnpm --filter @lola/api exec tsc --noEmit` clean; web typecheck clean (`pnpm --filter @lola/web exec tsc --noEmit`, or the repo's web typecheck task).
- `pnpm --filter @lola/flowmap build` clean (the package compiles `./core`/`./next`/`./xstate` to `dist`; `./react` ships as source and is transpiled by web via `transpilePackages`). Build the package BEFORE the web/api generator imports it.
- A new prisma migration for `FlowmapThumbnail` exists under `apps/api/prisma/migrations/` and `prisma generate` has been run.
- `apps/web/public/flowmap-thumbs/*` deleted; `apps/web/public/flowmap.json` has NO `preview.thumbnail` entries.
- Conventional-commit message(s) on this branch describing the WHY. Subject lowercase after the colon (commitlint). e.g. `feat(flowmap): store node thumbnails in storage brain, refresh live + via ci`.

## Constraints

- Stay in this worktree. Do not modify files outside it. Do not push to any remote. The operator handles push + PR + merge.
- Keep `@lola/flowmap` app-agnostic: no lola API URL, no Storage Brain client, no seed-user auth inside the package. Inject everything via the optional `resolveThumbnailUrl` / `onCaptureThumbnail` props.
- No em-dashes (U+2014) or en-dashes (U+2013) anywhere. Use colons, parentheses, commas, periods.
- `/admin` is locale-free: do NOT route to it via the i18n navigation helper (it prefixes the locale and 404s).
- The `STORAGE_BRAIN_API_KEY` / `STORAGE_BRAIN_BASE_URL` are operational secrets in Infisical; reference them only via the existing config/env validation, do not hardcode or add them yourself.

## Notes: running the migration (IMPORTANT, avoids shared-DB drift)

This worktree shares the Docker postgres (`lola-stories-postgres-1`, port 5432) with the main repo and other worktrees. Running `prisma migrate dev` against the shared `lola_stories` DB can fail with a DRIFT error. Use a dedicated per-worktree database for the migrate command ONLY:

```bash
docker exec lola-stories-postgres-1 psql -U lola -d lola_stories \
  -c "CREATE DATABASE lola_orch_flowmap_a;"
DATABASE_URL='postgresql://lola:lola_dev@localhost:5432/lola_orch_flowmap_a' \
  pnpm --filter @lola/api exec prisma migrate dev --name add_flowmap_thumbnail
```

(`lola_dev` is the committed local-dev password from `docker-compose.yml`; verify there if the connection fails. The `lola` role has `rolcreatedb` so Prisma can make its shadow DB.) The generated `migration.sql` is identical to what the shared DB would produce. Do NOT "fix" any drift error by copying another branch's migration file into this branch: that contaminates the branch. Always isolate via the dedicated DB. Optionally drop it when done: `docker exec lola-stories-postgres-1 psql -U lola -d lola_stories -c "DROP DATABASE lola_orch_flowmap_a;"`.

## Notes: general

- Worktree setup the orchestrator already did the checkout; you still need `pnpm install` (this slice ADDS `html-to-image`, so install is required), then `pnpm --filter @lola/api exec prisma generate`, then `pnpm --filter @lola/flowmap build` before web/api typecheck.
- Do NOT merge a half-wired thumbnail path: if `resolveThumbnailUrl` is wired but the upload path is not, the board shows blanks. Land A1+A2+A3+A4 together as one coherent slice.
- If anything here contradicts current repo conventions, prefer the repo conventions and record the deviation via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message that Slice A is complete, listing the new endpoint, the model/migration, the package props added, and confirming the committed thumbnails are gone and `flowmap.json` is structural.
