---
task: studio-source-nodes
depends_on: [studio-texture-prompt-gap]
shared_state: [authoring]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Add two CANVAS-ONLY source nodes for Figma-Weave-style fan-out: (1) an image-source node (Cmd+V pastes a clipboard image onto the canvas, its `image` output wires into image-consuming model nodes), and (2) a standalone prompt-source node (holds a prompt, its `text` output wires into MANY model nodes' prompt inputs, so one prompt can be compared across models). Ship BOTH in this one PR (they share the same foundation). The original mid-brainstorm spec is `docs/specs/2026-06-22-source-nodes-handover.md` (it may be uncommitted on main; the full decided design is reproduced below, so build from THIS goal).

## Confirmed architecture (do not deviate)

**Source nodes are CANVAS-ONLY; their value bakes to a `literal` on the downstream node at assemble time. ZERO engine/executor change.** A wire from a source node is NOT a `ref` to an engine node. `assembleDefinition` (and `buildSingleNodeDefinition`) inline the source's value as `{ kind: "literal", value }` on each downstream input. This reuses the existing literal-baking pattern (the same one `startPartialRun` uses to bake out-of-selection refs). One prompt node -> N model nodes, each gets the same literal text. The engine `WorkflowDefinition` never contains source nodes.

**Prompt-wire REPLACES the inline field.** When a prompt node is wired into a model node's prompt input, that model node's inline prompt textarea is replaced by a small read-only chip ("prompt: from <node>"); the wired text is the single source of truth. Unwire -> type inline again. Mirrors how image wires already work.

## The four design decisions (resolved; build to these, do not re-open)

1. **Persistence: `canvasLayout` FULLY owns source nodes AND their edges.** Since source nodes are absent from the engine def, `CanvasLayoutNode` persists their `kind` + value (image url / prompt text) and the source->model edges. Save / reload / fork is lossless on the EDITABLE canvas. ACCEPTED v1 tradeoff: anything rendering from the engine def alone (the read-only `WorkflowCanvas`, the run overlay) will NOT show source nodes (their values were baked into the model nodes). Flag this in the UI copy where natural; do not try to solve it in v1.
2. **How to add nodes:** image via Cmd+V paste (plus optional drag-drop of an image file, same upload path); prompt via a new "Sources" group in the add-node palette with a "Prompt" button. Confirm the palette grouping = one new "Sources" group.
3. **Image paste UX:** on paste, immediately create the image-source node showing a `data:` URL PREVIEW with an "uploading..." state; upload via `POST /api/images` to get a real URL; swap the node to hold the uploaded URL. WIRING and RUN are guarded until the upload completes.
4. **v1 scope:** ship BOTH source nodes in this one PR.

## Read first

- `src/lib/workflow/authoring.ts` (`assembleDefinition`, `buildSingleNodeDefinition`, `portBinding`, `wireInputPorts`, `canConnect`, `bindingKeyToPort`, `literalPrompt`, `taskAllowsPrompt`)
- `src/lib/workflow/canvas-layout.ts` (`canvasLayoutSchema`, `CanvasLayoutNode`, `canvasToLayout`, `definitionToCanvas`, the lossless round-trip and the `lossy` fallback)
- `src/lib/workflow/graph.ts` (`WorkflowNodeData`) and `src/lib/canvas/dirty.ts` (`computeDirty`)
- `src/components/workflows/EditableWorkflowCanvas.tsx` (palette, `addNodeAt`, `isValidConnection`/`connect`, the paste/clipboard surface)
- `src/components/workflows/EditableNodeCard.tsx` (node card anatomy: model header, prompt textarea, `NodePort` rows, `NodeMedia`)
- `src/components/canvas/NodePort.tsx` and `packages/lumitra-core/src/models/ports.ts` (`TASK_PORTS`, `PORT_COLOR`, the `text`/`image` port types and colors)
- `src/components/PromptInput.tsx` (`handlePaste` ~lines 142-150, the clipboard-image read to reuse)
- `src/hooks/useChat.ts` (~line 37, the `/api/images` upload + persist helper to reuse)
- `src/app/api/images/` (the upload route; returns a real URL)
- `packages/lumitra-core/src/jobs/types.ts` (`GenerateVideoJobInputSchema.inputImageUrl` / `Generate3DJobInputSchema.inputImageUrl` are `z.string().url()` -> a `data:` URL FAILS validation; this is why paste must upload first)

## Implementation plan (build all of it)

1. **Node-kind discriminator (canvas side only).** Add `kind: "task" | "image-source" | "prompt-source"` to the canvas node data and to `CanvasLayoutNode`. Source nodes are NOT `ModelTask`s; do NOT add pseudo-tasks to the `ModelTask` taxonomy. Source nodes carry their value (`imageUrl?` / `text?`), have NO model, NO Run button, and never become engine `WorkflowNode`s.
2. **`canvas-layout.ts` owns source nodes + edges.** `canvasToLayout` / `definitionToCanvas` round-trip source nodes and their source->model edges purely from the layout (the engine def has no entry for them). Save / reload / fork is lossless on the editable canvas.
3. **Make `text` a wireable port.** Extend `wireInputPorts` (currently image/mesh3d/video/audio) to include `text`. `portBinding(task, "text")` -> the model node's prompt key (`{ key: "prompt", path: "text" }` or the source-value path as appropriate). `bindingKeyToPort("prompt") -> "text"`. `canConnect` then allows a prompt-source `text` out -> a model node's `text` in. Reuse the texture-prompt task-prompt wiring just landed in `studio-texture-prompt-gap` (this task depends on it).
4. **`assembleDefinition` + `buildSingleNodeDefinition`: bake source wires to literals.** For a wire whose SOURCE node is a source-kind: image-source -> downstream `inputImageUrl` / `parentAssetId` = `literal(imageUrl)`; prompt-source -> downstream `prompt` (or `texturePrompt` for a texture node) = `literal(text)`. Source nodes are SKIPPED when emitting `wfNodes`. A model node with a wired prompt does NOT also emit its inline prompt.
5. **`EditableNodeCard.tsx`: render source nodes.** image-source: image preview + an `image` output port, no model picker / no Run, an "uploading..." state until the URL resolves. prompt-source: a textarea + a `text` output port, no model picker / no Run. For a model node whose prompt is wired: replace the inline textarea with the read-only "prompt: from <node>" chip.
6. **`EditableWorkflowCanvas.tsx`: Cmd+V paste + Sources palette.** Add a paste handler (reuse `PromptInput.handlePaste`): on Cmd+V with an image, create an `image-source` node at the viewport center holding a `data:` preview + "uploading...", upload via `/api/images` (reuse the `useChat.ts` persist helper), then swap to the uploaded URL; guard wiring/run until then. Add a "Sources" palette group with a "Prompt" button that creates a `prompt-source` node. Optionally also accept drag-drop of an image file (same upload path) if cheap.
7. **`dirty.ts` + every node iteration tolerate source-kind nodes** (no `task`, no `model`): no crashes, sensible dirty diffing.

## CRITICAL constraints (discovered, must hold)

- **Pasted images MUST be uploaded to a real URL before wiring/running.** `inputImageUrl` is `z.string().url()`; a `data:` URL fails validation. Paste -> upload via `/api/images` -> URL, THEN the node holds the URL. Guard wiring/run until upload completes.
- **image-source -> image-to-image / image-edit is BLOCKED in v1.** Those need `inputImages` as an ARRAY and the binding grammar has no array-of-refs yet (`portBinding` returns null). An image source CAN feed image-to-video, image-to-3d, multiview-to-3d, upscale, background-remove, image-to-text, image-to-json (single `inputImageUrl`/`parentAssetId`), but NOT image-to-image / image-edit. Leave those wires un-connectable in v1 (`canConnect` returns false); do not build array binding.
- Do NOT add a Prisma migration or change the engine `WorkflowDefinition` schema. Source nodes live only in `canvasLayout`.

## Definition of done

- Cmd+V pastes a clipboard image -> an image-source node appears, uploads, and its `image` output wires into a model node, baking `inputImageUrl` as a literal on assemble.
- A "Sources" palette "Prompt" button creates a prompt-source node; wiring its `text` output into N model nodes bakes the same prompt literal onto all N; each model node shows the read-only "prompt: from <node>" chip while wired.
- Save -> reload -> fork round-trips source nodes + their edges losslessly via `canvasLayout`.
- An image-source -> image-to-image/edit connection is rejected by `canConnect`.
- Tests: paste-creates-node-after-upload; one prompt node fans out to N literals; round-trip is lossless; image-to-image/edit wire blocked; assemble skips source nodes from `wfNodes`.
- the `verify` gate passes; single conventional commit describing the WHY.

## Constraints

- ZERO engine/executor change; bake to literals only. Do not touch `advanceWorkflow`.
- No pseudo-tasks in the `ModelTask` taxonomy.
- No em-dashes or en-dashes in new code, strings, or comments.
- Stay in this worktree. Do not push or merge.
- When done, output a final message that the task is complete.
