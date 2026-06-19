---
task: lumitra-studio-canvas-audio
spec: docs/specs/2026-06-19-multimodal-canvas-ui.md
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Phase 2 of "expose the multi-modal backbone in the studio UI": make AUDIO GENERATION authorable + runnable + viewable on the node canvas, mirroring how video was shipped in PR #63 (the task-native backbone + video). Scope is the two audio-PRODUCING tasks that yield an Audio asset: `text-to-audio` (Suno music via KIE) and `text-to-speech` (ElevenLabs TTS). The audio providers, catalog entries, JobKinds (`generate_audio`, `synthesize_speech`), and async completion path already exist and are merged; this slice is the UI + result surface only.

Do NOT include `speech-to-text` or any text/json-output task in this slice: those produce text on the job output (not a binary asset) and need a different result surface (the text/json node-card surface), which is Phase 3.

## Read first

- The spec: `docs/specs/2026-06-19-multimodal-canvas-ui.md` (the "Later phases" section: Phase 2 audio).
- How video was done (the pattern to mirror), via `git log` and these files:
  - `src/lib/workflow/authoring.ts`: `CANVAS_AUTHORABLE_TASKS`, `PROMPT_REQUIRED`/`PROMPT_OPTIONAL`, `taskNeedsPrompt`, `taskRequiresPrompt`, `portBinding`, `defaultModelForTask`. `taskToJobKind` already maps `text-to-audio` -> `generate_audio` and `text-to-speech` -> `synthesize_speech`.
  - `src/lib/workflow/run-status.ts`: `NodeResultKind` (currently `image|video|model3d|unknown`) and `NodeResult`.
  - `src/lib/workflow/result-kind.ts`: `resultKind(mime, url)` server-side mapping; `toNodeResult`.
  - `src/components/workflows/NodeMedia.tsx`: the result-media switch on `result.kind` (image/video/model3d/else). The video branch is the template.
  - `src/components/workflows/NodeResultLightbox.tsx`: the lightbox switch (image/video/else).
  - `packages/lumitra-core/src/models/catalog.ts`: the audio entries (`kie/suno-v5` text-to-audio isDefault, `elevenlabs/tts-multilingual-v2` text-to-speech isDefault) and `packages/lumitra-core/src/models/ports.ts` (TASK_PORTS: text-to-audio + text-to-speech both `inputs:['text'], output:'audio'`).
- The catalog is already correct; do not edit `packages/lumitra-core` unless a genuine bug blocks the slice.

## Definition of done

1. **Result kind.** Add `"audio"` to `NodeResultKind` (`run-status.ts`). In `result-kind.ts`, map `audio/*` mime types (and audio extensions `mp3, wav, m4a, ogg, aac, flac`) to `"audio"`.
2. **Result rendering.** In `NodeMedia.tsx`, add an `else if (result.kind === "audio")` branch that renders a native `<audio controls>` player (with the same re-sign-on-error pattern the image/video branches use). In `NodeResultLightbox.tsx`, add an audio branch rendering `<audio src controls>`. Keep the dark Tailwind studio style; match the existing branches' classes.
3. **Authorable.** Add `text-to-audio` and `text-to-speech` to `CANVAS_AUTHORABLE_TASKS` and to `PROMPT_REQUIRED` in `authoring.ts` (both are prompt-only: a music description / the text to speak; no upstream wire, so no `portBinding` entry needed). They become buildable in the add-node palette automatically (catalog + taskToJobKind already satisfied).
4. **Defaults.** Confirm `defaultModelForTask("text-to-audio")` and `("text-to-speech")` resolve (Suno V5 / ElevenLabs Multilingual v2). No change expected.
5. **Palette help text** (`EditableWorkflowCanvas.tsx`): the line currently says "Audio and vision tasks land in a later pass." Update it so it no longer excludes audio (e.g. "Vision tasks land in a later pass.").
6. **Tests.** Mirror the video tests:
   - `authoring.spec.ts`: assert `isBuildableTask("text-to-audio")` and `("text-to-speech")` are true; `taskRequiresPrompt` true for both; `taskToJobKind` mappings; a `EditableWorkflowCanvas.spec.tsx` palette assertion that "Text to Audio" and "Text to Speech" now appear (and update the prior assertion that expected them absent).
   - `result-kind` test: `audio/mpeg` and `.mp3` map to `"audio"`.
   - An assembleDefinition test: a `text-to-audio` node with a prompt assembles to a `generate_audio`-bound node; blocks with no prompt.
7. The full `verify` gate passes (see frontmatter): db:generate + package build + `pnpm test` + `tsc --noEmit` + `pnpm lint` (0 errors).
8. Single commit, conventional-commit message, `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

## Constraints

- Stay in this worktree. Do not push to any remote (the operator opens the PR).
- TypeScript strict. **No em-dashes or en-dashes anywhere** (use colons, parentheses, commas, periods). Match the dark Tailwind studio style.
- Do NOT touch the backbone (providers/jobs/catalog) or `speech-to-text` / vision / director tasks: those are later phases. Keep `CANVAS_AUTHORABLE_TASKS` limited to image/3D/video (existing) + the two audio-producing tasks.
- `isBuildableTask` stays a UI-readiness gate distinct from `taskToJobKind`: only add the two audio tasks whose result (Audio asset) the node card can now render. Do NOT add `speech-to-text` (no audio result; text output, Phase 3).
- The async completion path (webhook + the run-status fallback poll added in PR #63) already covers `generate_audio`; do not re-implement it.

## Notes

- `synthesize_speech` (TTS) is SYNC (ElevenLabs returns bytes inline -> Audio asset in the worker); `generate_audio` (Suno) is ASYNC (completes via webhook / the run-status fallback poll). Both produce an Audio asset, so both render via the new `kind==="audio"` branch. No per-task UI difference is needed beyond the shared audio result surface.
- If you find a pre-existing tiny issue in the touched files, fix it in the same commit (no open follow-ups). If it is bigger than the slice, record an `open_thread`.
