---
task: studio-node-settings-sidebar
spec: docs/specs/2026-06-26-node-settings-sidebar.md
shared_state: [authoring]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Implement the leaf spec at `docs/specs/2026-06-26-node-settings-sidebar.md` (already committed in this worktree, status: decided). Add a Figma-Weave-style right settings sidebar to the node canvas: select a model node, get a panel with that modality's generation knobs (aspect ratio, resolution, seed) and a "Runs" count (N runs -> N history entries), plus an estimated cost and a Run button. Read the spec IN FULL first; it is the source of truth. This summary exists so you do not drift from it.

## Read first

- `docs/specs/2026-06-26-node-settings-sidebar.md` (the full design: data model, settings source, persistence, baking, runs execution, sidebar UX, tests, non-goals)
- `packages/lumitra-core/src/models/types.ts` (`MODEL_TASKS`, `Modality`) and `catalog.ts` (per-model `cost`/`usd` for the estimate)
- `packages/lumitra-core/src/jobs/types.ts` (the `.passthrough()` option bags: `GenerateImageJobInputSchema`, `GenerateVideoJobInputSchema` / `GenerateVideoOptionsSchema` already carry `duration`/`resolution`/`aspectRatio`, `GenerateAudioJobInputSchema`; confirm the EXACT nesting of options before baking)
- `src/lib/workflow/canvas-layout.ts` (`AuthorNode` / `CanvasLayoutNode` / `EditableLayoutNode`, `canvasToLayout`, `definitionToCanvas`; round-trip `settings` exactly like `prompt`)
- `src/lib/workflow/authoring.ts` (`assembleDefinition`, `buildSingleNodeDefinition`; bake `settings` into the job options input)
- `src/lib/workflow/executor.ts` (`startPartialRun`, `enqueueNode`; the N-runs loop + per-run seed)
- `src/app/api/v1/workflows/run/route.ts` (add the `runs` param)
- `src/components/workflows/EditableWorkflowCanvas.tsx` (mount the panel on single-node selection) and `EditableNodeCard.tsx` (the existing inline Run stays runs=1)
- `src/lib/canvas/dirty.ts` (settings changes mark dirty)

## Definition of done (per the spec)

1. **`NODE_SETTINGS`** map by `Modality` in `packages/lumitra-core/src/models/` (image: aspectRatio + resolution + seed; video: aspectRatio + resolution + duration; audio: duration; 3D/vision/utility: none). Each knob: type (select/number/seed), default, options/range. Exported + unit-tested for shape.
2. **Persistence:** `AuthorNode` / `CanvasLayoutNode` / `EditableLayoutNode` gain optional `settings: Record<string, unknown>`; `canvasToLayout` / `definitionToCanvas` round-trip it like `prompt` (Zod-bounded). NO Prisma migration (lives in `params.canvasLayout`).
3. **Baking:** `assembleDefinition` + `buildSingleNodeDefinition` bake a node's settings into the job's options input (`inputs.options = { kind: "literal", value: mergeWithModelDefaults(settings) }`, matching the schema's real nesting). Unset knobs fall back to model/catalog defaults so an untouched node behaves EXACTLY as today (zero regression). `seed`: when random/unset, leave it out so each run resolves a fresh seed; when pinned, bake the literal.
4. **Runs (N -> N history entries):** `run` route accepts optional `runs` (default 1, clamp 1..8); for `runs=N` the server performs N single-node partial runs of that node, each reusing the existing assemble -> `startPartialRun` -> `enqueueNode` -> `advanceWorkflow` -> history-append path verbatim (NO new completion logic). For random seed, vary the seed per iteration so the N samples differ; for a pinned seed, all N use it.
5. **Sidebar:** `NodeSettingsPanel.tsx` mounted in `EditableWorkflowCanvas.tsx`, shown when exactly one TASK node is selected. Renders the modality's knobs, a Runs stepper (1..8), an estimated cost (catalog per-gen cost x Runs), and a Run button that runs that node with the Runs count. Editing a knob updates `settings` + marks dirty. Multi-select (>1 node): collapse to just the Runs stepper + "Run selected" (existing multi-select path). A modality with no knobs shows "No model settings" + Runs + Run. Source nodes (no model) show no panel.
6. **Tests:** settings round-trip; assemble bakes settings into options + defaults fallback (zero-regression); random seed varies per run, pinned holds; the run route enqueues N node-runs for `runs=N`, each appending a generation; the panel renders the right knobs per modality.

## Constraints

- NO Prisma migration; NO change to `advanceWorkflow`'s readiness/finalize math; NO new completion logic.
- If you touch the published `@marlinjai/studio-core` job schema, the verify gate rebuilds packages; keep changes minimal (the option bags already exist).
- Non-goals (do NOT build): per-model option schemas, settings presets, credits display (show USD), 3D/vision/utility knobs. File any tempting extras as `open_thread`.
- No em-dashes or en-dashes in any new code, string, or comment.
- Stay in this worktree. Do not push or merge. When done, output a final message that the task is complete.
