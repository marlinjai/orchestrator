---
task: lola-trello-attachment-fix
spec: (none — implement from this goal)
---

# Goal

Fix the broken Trello screenshot attachment URL in lola-stories' feedback
delivery flow. Today the card gets `http://api/v1/files/<id>` (internal Docker
hostname leak from storage-brain), which is unreachable to admins reviewing
Trello.

Use the new `getPermanentUrl(fileId)` method on `@marlinjai/storage-brain-sdk`
(version >=0.9.0 — just published) to obtain a permanent, public HMAC-signed
URL for each screenshot, and use that as the Trello attachment URL.

Additionally: include the `storageFileId` for each screenshot in the Trello
card description, so an admin can always regenerate URLs later via a future
admin endpoint or by querying the DB.

## Read first

- `apps/api/src/modules/storage/storage.service.ts` (add new method here)
- `apps/api/src/modules/feedback/feedback-delivery.service.ts` (consumer)
- `apps/api/src/modules/feedback/feedback-delivery.service.spec.ts` (tests; respect TDD)
- `apps/api/src/modules/feedback/feedback.module.ts` (DI wiring; StorageModule is @Global per existing comment)
- `apps/api/src/modules/storage/storage.module.ts` (where StorageService is provided)
- `apps/api/node_modules/@marlinjai/storage-brain-sdk/dist/index.d.ts` — confirm `getPermanentUrl` signature in installed version
- `.claude/rules/tdd.md` (TDD rule in repo)
- `CLAUDE.md` in repo root

## Definition of done

1. **Bump SDK** in `apps/api/package.json` to `^0.9.0` (or whatever the latest published is — check `npm view @marlinjai/storage-brain-sdk version`). Run `pnpm install` at the workspace root so the lockfile updates.
2. **Add `StorageService.getPermanentUrl(fileId)`** wrapping `client.getPermanentUrl(fileId)`. Same logger pattern as existing `getSignedUrl`. Return `{ url: string }`.
3. **Update `FeedbackDeliveryService`**:
   - Inject `StorageService`.
   - In `runDelivery`, when iterating `feedback.screenshots`, call `storage.getPermanentUrl(screenshot.storageFileId)` and pass that `url` to `trello.attachUrl(card.id, url)`. Fallback to the stored `screenshot.url` only if `getPermanentUrl` throws (defensive — better to attach a broken link than no link at all).
4. **Update `buildCardDescription`** to include a **Screenshot file IDs:** line listing each `storageFileId` (one per line). Empty section omitted if no screenshots. KEEP the existing `**URL:** ${feedback.pageUrl}` line — it's useful for DB lookups even if admin can't load the page directly.
5. **Tests** (TDD, write first):
   - `feedback-delivery.service.spec.ts`: mock StorageService with `getPermanentUrl` returning a fixed URL; assert `trello.attachUrl` is called with that URL not `screenshot.url`. Also assert description contains `**Screenshot file IDs:**`. Add a fallback test: when `getPermanentUrl` rejects, `attachUrl` is still called with `screenshot.url`.
   - Run `pnpm --filter @lola/api test` — must pass.
   - Run `pnpm --filter @lola/api typecheck` — must pass.
6. **Single conventional-commit**: `fix(feedback): attach permanent storage-brain URLs to Trello + log file IDs in description`.
7. **Open a PR** against `main` titled "fix(feedback): permanent storage URLs for Trello attachments". Body has Summary + Test plan sections, references the storage-brain `getPermanentUrl` shipped in SDK 0.9.0.

## Constraints

- Stay in this worktree.
- Do NOT touch the feedback frontend (it just shipped in PR #123).
- Do NOT modify storage-brain (it just shipped in PR #1).
- Do NOT push to main. Push the feature branch and open a PR via `gh pr create`.
- Do NOT introduce a new env var for the storage-brain URL — the SDK already builds full URLs from PUBLIC_BASE_URL on the server side.
- If `npm view @marlinjai/storage-brain-sdk version` returns less than 0.9.0, STOP and escalate — the publish must have failed.

## Notes

- Marlin's project rule: no em-dashes / en-dashes in any new text. Use colon, parentheses, or split sentences.
- The `**URL:** ${feedback.pageUrl}` field has been confirmed as intentionally kept (Marlin uses the deep-link family/story IDs in the path for DB queries even when he can't load the page).
- After commit and PR open, output a final message with branch name + PR URL.
