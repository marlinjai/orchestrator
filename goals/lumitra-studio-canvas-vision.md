---
task: lumitra-studio-canvas-vision
spec: docs/specs/2026-06-19-multimodal-canvas-ui.md
depends_on: [lumitra-studio-canvas-audio]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Phase 3: make the VISION + UTILITY + text/json-output tasks authorable + runnable + viewable on the node canvas. This adds the text/json result surface (the thing audio/video did not need) plus image-wire bindings for the utility tasks. Backbone (providers/catalog/JobKinds `analyze_image`, `transform_image` + the sync result mapping) is already merged; this is UI + result surface + wiring only.

Tasks in scope:
- `image-to-text` (caption -> text on job output, NO asset)
- `image-to-json` (structured extraction -> json on job output, NO asset)
- `speech-to-text` (transcript -> text on job output, NO asset; audio input)
- `upscale` and `background-remove` (each -> a NEW Image asset; image input)

## Read first

- Spec `docs/specs/2026-06-19-multimodal-canvas-ui.md` (Phase 3).
- The audio slice that just merged (`git log` for `lumitra-studio-canvas-audio`): the same files + the `kind` branch pattern.
- `src/app/api/v1/workflows/runs/[id]/route.ts`: builds `results[]` ONLY from `nr.resultAssetId` today. Text/json tasks have no asset (their output is on `nr.output.text` / `nr.output.json`), so this route must also surface those.
- `src/lib/workflow/run-status.ts` (NodeResultKind, NodeResult), `result-kind.ts`, `NodeMedia.tsx`, `NodeResultLightbox.tsx`.
- `src/lib/workflow/authoring.ts`: `CANVAS_AUTHORABLE_TASKS`, `portBinding` (image -> inputImageUrl exists for image-to-3d/image-to-video; mesh -> parentAssetId for remesh/texture), `wireInputPorts`, `taskNeedsPrompt`/`taskRequiresPrompt`, `bindingKeyToPort`.
- `packages/lumitra-core/src/models/ports.ts` TASK_PORTS for these tasks; the job input schemas in `packages/lumitra-core/src/jobs/types.ts` (`AnalyzeImageJobInputSchema` uses `inputImageUrl`/`inputImage`+optional `prompt`; `TranscribeJobInputSchema` uses `inputAudioUrl`; `TransformImageJobInputSchema` uses `parentAssetId`).

## Definition of done

1. **Text/json result surface.** Add `"text"` and `"json"` to `NodeResultKind`. Extend the run-status route so a succeeded node-run with no asset but with `output.text` (image-to-text, speech-to-text) or `output.json` (image-to-json) yields a `NodeResult` of kind `text`/`json` carrying the value (a new optional `text`/`json` field on `NodeResult`, since there is no signed url). `NodeMedia.tsx` renders text in a scrollable read-only box and json in a `<pre>` (truncated with expand to the lightbox); `NodeResultLightbox.tsx` shows the full text/json. Re-sign logic does not apply to text/json (no url).
2. **Utility tasks (image -> Image asset).** Add `upscale` + `background-remove` to `CANVAS_AUTHORABLE_TASKS`. Add a `portBinding` case: `image` port + (`upscale`|`background-remove`) -> `{ key: "parentAssetId", path: "assetId" }` (TransformImage takes the source Image asset by id). These produce Image assets, already renderable. They take an image WIRE (no prompt): not in PROMPT_REQUIRED.
3. **Vision/text tasks.** Add `image-to-text`, `image-to-json` to `CANVAS_AUTHORABLE_TASKS`; image wire -> `inputImageUrl` (extend the existing image-port portBinding branch to include them, matching AnalyzeImage's `inputImageUrl`). `image-to-json` allows an optional extraction `prompt`; `image-to-text` takes no prompt. Add `speech-to-text` to `CANVAS_AUTHORABLE_TASKS`; audio wire -> `inputAudioUrl` (new portBinding case for the `audio` port + `speech-to-text`; add `audio` to `wireInputPorts` filter and `bindingKeyToPort("inputAudioUrl") -> "audio"`).
4. **Palette help text**: drop the "Vision tasks land in a later pass" note (everything is now authorable); replace with a neutral hint or remove.
5. **Tests.** Extend `authoring.spec.ts` (buildable + portBinding for the new tasks + audio/image wire bindings), `EditableWorkflowCanvas.spec.tsx` (palette now shows Upscale, Background Remove, Image to Text, Image to JSON, Speech to Text), a `result-kind`/run-status test for text/json results, and an assembleDefinition test for an image->upscale wire and an audio->speech-to-text wire.
6. Full `verify` gate green. Single conventional commit with the Co-Authored-By trailer.

## Constraints

- Stay in this worktree; do not push. TypeScript strict. No em-dashes/en-dashes. Dark Tailwind studio style.
- Do NOT touch the backbone (providers/jobs/catalog) or director routes (Phase 4).
- Keep the zero-input guard honest: a vision/utility node with no wired input (and no prompt) must still be blocked at assemble time.
- `isBuildableTask` stays the UI-readiness gate: only add tasks whose result the node card can now render (which, after this slice, is all of image/3D/video/audio/text/json/utility). `text-generation`, `speech-to-speech`, `segmentation` stay OUT (no job/result path).

## Notes

- The text/json surface is the main design call: keep it simple and legible (monospace `<pre>` for json, wrapped text box for captions/transcripts), copy-to-clipboard is a nice-to-have not a requirement.
- Record an `open_thread` for anything genuinely bigger than this slice; fix tiny pre-existing issues inline.
