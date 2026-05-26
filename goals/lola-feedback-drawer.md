---
task: lola-feedback-drawer
spec: (none — implement from this goal)
---

# Goal

Rebuild the in-app feedback UI in lola-stories from a centered modal into a
right-side drawer that does NOT cover the screen, so users can keep reading
the content they're describing while they write. Add draft caching to
localStorage so accidental close / reload does not lose typed text. Add
drag-and-drop and Cmd+V/Ctrl+V paste support for screenshots. Move the
floating trigger button from bottom-right to top-right so it doesn't collide
with the macOS screenshot floater that appears bottom-right.

## Read first

- `apps/web/src/components/feedback/FeedbackWidget.tsx` (floating button + open flow)
- `apps/web/src/components/feedback/FeedbackModal.tsx` (current modal — this is what becomes the drawer)
- `apps/web/src/lib/feedback.ts` and `apps/web/src/lib/feedback-capture.ts`
- `apps/web/messages/de.json` and `apps/web/messages/en.json` — search for `"feedback"` key
- `CLAUDE.md` in repo root
- Existing tests under `apps/web/src/components/feedback/` (none currently, but check)

## Definition of done

UI changes:
1. **Drawer instead of modal.** Replace the centered overlay with a right-side panel: fixed top-0 right-0 h-full w-full sm:w-[420px], slides in from the right, has a subtle backdrop (low opacity) so the page is still readable behind it. Page must remain interactive while drawer is open (no body scroll lock). Esc still closes.
2. **Draft caching.** message + type + includeAuto are persisted to localStorage on every change under key `lola.feedback.draft.v1`. On open, draft is restored. On successful submit, draft is cleared. (Screenshot blob does NOT persist — Blobs can't be serialized. That's fine; the auto-capture re-runs each open.)
3. **Cmd+V / Ctrl+V paste.** When the drawer is open and focus is inside it, pasting from clipboard with image data adds it to `uploads`. Same `MAX_UPLOADS=4` + `MAX_FILE_BYTES=5MB` limits apply.
4. **Drag and drop.** The drawer has a drop zone (could be the existing "Add screenshot" area or the whole upload section). Dropped image files are added to uploads with same limits.
5. **Button position.** Move the floating button from `fixed bottom-20 right-4 sm:bottom-6` to `fixed top-20 right-4` (just below typical topbars). Keep the same icon, size, and hover behavior.
6. **Keep retake hide-during-capture behavior.** Existing `handleRetake` flow still works (drawer hides itself during the recapture).

Tests:
- Unit test (jest or whatever the apps/web uses): localStorage cache writes on input, restores on mount, clears on successful submit. Use a mock fetch / api client.
- Unit test: paste event with `image/png` clipboard item adds a file to uploads.
- Unit test: drop event with image files adds them to uploads, ignores non-image files.
- Unit test: button renders at top-right.
- `pnpm --filter @lola/web test` (or whatever the web test command is — check repo CLAUDE.md / package.json) passes.
- `pnpm --filter @lola/web typecheck` passes.
- `pnpm --filter @lola/web lint` passes.

Hygiene:
- No emojis in code/comments unless they already exist there.
- No em-dashes or en-dashes in new text (project convention). Use colon, parentheses, or split into two sentences.
- Translations: if any new user-facing strings are added (drop-zone label, paste hint, etc), add them to BOTH `de.json` and `en.json` under the existing `feedback` key. Match the file's formatting (Prettier + ascii-escaped). If unclear, look at `pnpm --filter @lola/web i18n:check` for the parity guard.
- Single conventional-commit on the branch ("feat(feedback): drawer UI with draft cache, paste, drag-drop, top-right trigger").
- Open a PR against `main` titled "feat(feedback): drawer with draft cache + paste + drag-drop".

## Constraints

- Stay in this worktree.
- Branch name: `feat/feedback-drawer-ux` (or whatever the worktree is created on).
- Do NOT push directly to main. Push the feature branch and open a PR via `gh pr create`.
- Do NOT touch the feedback BACKEND (apps/api/src/modules/feedback/*). The Trello URL bug is a separate task. Stay in `apps/web/src/components/feedback/` + i18n messages + maybe a tiny localStorage helper.
- Do NOT change the feedback wire payload (FormData fields stay identical). Backend stays untouched.

## Notes

- Z-index: drawer should still be above the app content but does not need to overlay modals or toasts. Use the existing z-50 the modal had.
- Backdrop: very light (bg-ink/10 maybe, or none at all) so the user can still SEE the page they're describing. The whole point of this rework is "don't cover the screen".
- Reduced motion: respect `prefers-reduced-motion` for the slide-in animation.
- After commit and PR open, output a final message with branch name + PR URL.
