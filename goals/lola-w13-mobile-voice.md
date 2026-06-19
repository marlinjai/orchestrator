---
task: lola-w13-mobile-voice
verify: pnpm --filter @lola/web typecheck
verify_fix_cap: 2
---

# Goal

Fix the mobile error shown when selecting/previewing a voice in the premade voice library (`/onboarding/voice-first`). Root cause: `a.play()` is called without `await`/`.catch()`/`onerror`, so mobile autoplay-policy rejections surface as an error overlay; plus invalid nested interactive markup.

## Read first

- `apps/web/src/components/voice/PickPremade.tsx` (:72-85 `toggle`, esp. the unawaited `a.play()` at ~:82 and unconditional `setPlayingId` at ~:84; the nested `role="button"` span at :164-182 inside the parent select `<button>` at :127; the already-wrapped `pick()` POST at :87-107).
- `apps/web/src/components/voice/UploadVoice.tsx:31` (the good `a.onerror` reference pattern).

## Definition of done

1. Make `toggle` async: set `a.onended` and `a.onerror` to reset `playingId`; only call `setPlayingId(v.voice_id)` AFTER `await a.play()` resolves; wrap in try/catch that resets state on rejection.
2. Do NOT show a visible error for blocked autoplay (expected on mobile) - just reset the icon to the play state. Reserve a visible message only for real load failures via `a.onerror`. Reuse an existing error-display affordance if one is needed; do NOT add a new i18n message key (keep this task messages-free).
3. De-nest the markup: the outer selectable card becomes a `<div role="button" tabIndex={0}>` (or render the play control as a sibling), preserving Enter/Space activation and `stopPropagation` on the preview control so a preview tap does not also re-select.

## Acceptance criteria (incl. unhappy paths)

- Tapping a card on mobile selects it with no error overlay/toast.
- Tapping play with autoplay blocked -> icon returns to play, no error, no unhandled promise rejection.
- Play on a 404/blocked preview_url -> `onerror` fires, icon resets.
- Play while another preview plays -> previous pauses (single-playback invariant holds).
- The creation POST failure path still surfaces its existing localized error via `setError`.
- No nested interactive elements; preview tap does not bubble to re-select; keyboard activation works; desktop behavior unchanged.
- `pnpm --filter @lola/web typecheck` passes.

## Constraints

- Stay in this worktree. Do not push to any remote. Touch only `apps/web/src/components/voice/PickPremade.tsx` (and at most a tiny shared util if strictly needed).
- Do NOT edit `apps/web/messages/*.json` (keep this task messages-free so it stays parallel-safe).
- NO em-dash or en-dash. Single conventional commit. Output a final completion message.
