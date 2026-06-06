---
task: arbosano-phase-3-media
spec: plans/2026-05-30-phase-3-media-pipeline.md
marlin_proxy: shadow
---

# Goal

Implement arbosano content-as-code **Phase 3.2 to 3.4**: the admin media pipeline. An admin pastes an image in the `/admin` chat, it buffers to Storage Brain, gets sharp-optimized + EXIF-stripped, and lands as a content-addressed `public/media/<hash>.webp` in the session worktree, served live in the iframe. You are on branch `feat/phase-3-2-media`, stacked on `feat/phase-2-admin` (PR #9). Build to green (lint + tsc + build + fixtures). Do NOT push, do NOT open a PR, do NOT merge, do NOT deploy. The operator pushes and opens the stacked PR after review.

The authoritative spec is `plans/2026-05-30-phase-3-media-pipeline.md` (sub-phases 3.2, 3.3, 3.4). **Read it fully before writing code.** Sub-phase 3.1 already landed in PR #8; 3.5 (CI guards) is operator/Phase-5 territory, OUT OF SCOPE for you.

## Repo-state precondition

- You are on `feat/phase-3-2-media`, stacked on `feat/phase-2-admin`, which is stacked on `feat/phase-3-1-extractions`.
- Working tree clean at start. If not, escalate.
- These ALREADY EXIST and you MUST reuse them (never recreate, never re-extract):
  - `src/lib/media.ts` (#8): `ingestImage(buf)`, `optimizeToWebp(buf)`, `contentHash(buf)`, `MEDIA_NAME_REGEX` (`^[0-9a-f]{8}\.webp$`), `MAX_FILE_BYTES`, `COMMITTED_MEDIA_MAX_BYTES`, allowed-mime set. The sharp re-encode strips EXIF/GPS; content-hash is deterministic. Import these, do NOT reimplement the transform.
  - `src/lib/rate-limit.ts` (#8): `checkThrottle(ipHash, { limit, windowMs, bucket })` and `getClientIpHash(req)`.
  - `src/lib/dom.ts` (#8): `isTypingTarget`. The spec 3.4 says to lift it from `FeedbackWidget.tsx`; that is STALE, #8 already did it. Import from `src/lib/dom.ts`. Do NOT touch `FeedbackWidget.tsx`.
  - `src/lib/storage-brain.ts`: `getStorageBrain()` (returns null without the key, warn-and-continue) and `uploadBuffers(storage, inputs[])`. Do NOT modify storage-brain.ts.
  - `src/lib/worktree-sessions/` (Phase 2, on this stacked branch): `getSessionManager()` -> `.get(key)` returns `Session { key, branch, worktreePath, port, status }`.
  - `src/lib/admin/auth.ts` (Phase 2): `assertAdminApi(req)` gate.

## Verified contracts to trust (re-verified against the repo; do NOT guess these)

- `uploadBuffers(storage, inputs[])` takes per-item `{ buffer, filename, mimeType, context, tags? }`, NOT `(buffers, context, tags?)`.
- `getStorageBrain()` returns null when the key is absent. A bucket failure MUST warn-and-continue, never block the local `public/media` write (the bucket is transport, `public/` is the source of truth).
- `checkThrottle(ipHash, { limit, windowMs, bucket })` + `getClientIpHash(req)`.
- Phase 2's session manager is on this branch: resolve the worktree dir via `getSessionManager().get("default")?.worktreePath`. Since Phase 2 is present here, do NOT build the `ADMIN_WORKTREE_ROOT` stub the spec mentions; call the real session manager. (Keep a clear error if there is no active session.)
- `public/media/` is intentionally NOT gitignored (committed content).

## Build (sub-phase order)

### 3.2 Session worktree path resolution

`src/lib/admin/media-target.ts` exporting `resolveSessionMediaDir(session)` (or a session-key variant) returning the worktree's `public/media` absolute dir, joined off the Phase 2 session worktree root. HARD path-traversal fence: the resolved dir MUST be a child of the known worktrees base (realpath/resolve + containment check, reject otherwise) so a forged session can never write outside a worktree. `mkdir -p` on first write. Mirror the realpath-containment style of the Phase 2 `tools.ts` fence (resolve, then reject anything not contained under the base).

### 3.3 The ingest endpoint `POST /api/admin/media`

`export const runtime = "nodejs"` + `export const dynamic = "force-dynamic"`. Flow:
- `assertAdminApi(req)` first (return its Response if non-null).
- 409/401 if no active session, never crash.
- Read multipart form-data; enforce `MAX_FILE_BYTES` + allowed-mime (400 with a German message).
- `ingestImage(buf)` (the shared transform; EXIF/GPS stripped).
- Durability: `getStorageBrain()` + `uploadBuffers(storage, [{ buffer, filename, mimeType: "image/webp", context: "arbosano-admin-media", tags: { source: "admin-paste", sessionId } }])`, warn-and-continue on failure.
- Source of truth: write the buffer to `<sessionMediaDir>/<hash>.webp` (idempotent: same hash = same bytes = free dedupe).
- Rate-limit via `checkThrottle(getClientIpHash(req), { limit: 30, windowMs: 600000, bucket: "admin-media" })`.
- Respond `{ path: "/media/<hash>.webp", hash, width, height, bucketUrl }`.

### 3.4 Client paste/drop affordance + required alt

Extend the Phase 2 composer `src/app/(admin)/admin/page.tsx`: an `onPaste` handler reading `clipboardData.files`, a drag-drop zone, and a file button (gate keyboard handling with the existing `isTypingTarget` from `src/lib/dom.ts`). On paste: POST to `/api/admin/media`, show an uploading state, on 200 insert an attachment chip carrying `/media/<hash>.webp` AND a **required alt-text field** (alt is required; the human fills it, the agent never fabricates alt; block "send" while a chip has empty alt). The chat then carries the path + alt so the agent writes them into the content module's `image` field. No iframe code change (next dev serves the worktree `public/` live).

## Definition of done

- `pnpm exec eslint --max-warnings=0 .` + `pnpm exec tsc --noEmit` + `pnpm build` green.
- `pnpm test` still green (do not break the Phase 2 fixtures).
- A NEW fixture (`.mts` run via the existing `node --import ./scripts/tools-loader.mjs --experimental-strip-types` pattern, added to the `test` script): asserts (a) `resolveSessionMediaDir` REJECTS a forged/`../`/absolute session path (traversal fence), ACCEPTS a valid session resolving under the base ending in `/public/media`; (b) `ingestImage` produces a deterministic `<hash>.webp` (same input = same hash) and the re-encoded buffer has NO GPS/EXIF (assert via sharp metadata). Wire the new fixture into the `test` script in package.json.
- Commits on `feat/phase-3-2-media`, conventional, dash-safe. One commit per sub-phase is fine.
- `update_state(kind="commit")` after each commit; `kind="file_touched"` for new files; `kind="decision"` for non-obvious choices; `kind="open_thread")` for: the operator-run live paste->iframe verification, and the Phase 3.5 CI guards (media-lint, max-bytes, empty-alt) that the operator folds into publish-gate.yml.
- Final report: decisions taken, files added, open threads, and confirmation lint + tsc + build + the fixtures are green.

## Constraints

- Stay in this worktree. No files outside it. Do NOT push, open PRs, merge, deploy, or run the live `:3100` boot (operator does the live paste verification).
- No em-dashes (U+2014) / en-dashes (U+2013) anywhere (code, comments, commit messages). Use colons, parens, commas.
- Respect the never-auto-merge set in your OWN edits: do not touch `next.config.*`, `Dockerfile`, `entrypoint.sh`, `infra/**`, `.github/**`, `tsconfig.json`, `eslint.config.*`, auth/secrets. `package.json` is editable ONLY to add the new fixture to the `test` script (NO new dependencies: sharp + Storage Brain are already present; if you think you need a new dep, escalate).
- Secrets via Storage Brain SDK / Infisical only; reference `process.env`, never hardcode. The route warns-and-continues without `STORAGE_BRAIN_API_KEY`.
- Required-alt is a hard contract: a chip with empty alt must block send.

## Escalation rules

- Working tree not clean: escalate.
- The traversal fence cannot be made to fail closed: escalate.
- You believe a new dependency is required: escalate (the spec says none are needed).
- Scope creep beyond media-target.ts + the media route + the composer extension + the fixture: escalate.

## Out of scope (stated, not parked)

- Sub-phase 3.5 (publish-carries-binary verification + the media-lint / max-bytes / empty-alt CI guards): the CI guards touch `.github/**` (blocked) and fold into Phase 5; the operator adds them. Leave an open_thread.
- The live paste->iframe end-to-end test (operator-run, needs the :3100 boot).
- Phase 4 (better-auth), Phase 5.3 to 5.6 (publish pipeline GitHub App).
- Any push, PR, merge, or deploy.
