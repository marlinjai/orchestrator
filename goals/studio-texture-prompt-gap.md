---
task: studio-texture-prompt-gap
shared_state: [authoring]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Close the long-standing texture-prompt gap on the node canvas: a `texture` task node's typed prompt is currently SILENTLY DROPPED. Root cause: in `src/lib/workflow/authoring.ts`, `taskNeedsPrompt('texture')` is false, so neither `assembleDefinition` nor `buildSingleNodeDefinition` emits the prompt; and the texture-3D job field is `texturePrompt`, not `prompt`, so even a forced prompt would not land. Make a texture node's prompt flow to the `texture_3d` job's `texturePrompt` input. Deferred from canvas PR #51; this finishes it.

## Read first

- `src/lib/workflow/authoring.ts` (the canvas->definition compiler: `assembleDefinition`, `buildSingleNodeDefinition`, `portBinding`, `taskNeedsPrompt` / `taskRequiresPrompt` / `taskAllowsPrompt`, `literalPrompt`, `bindingKeyToPort`, `CANVAS_AUTHORABLE_TASKS`)
- `packages/lumitra-core/src/jobs/types.ts` (`Texture3DJobInputSchema` and its `texturePrompt` field; confirm the exact key and whether it is optional)
- `packages/lumitra-core/src/models/ports.ts` (`TASK_PORTS` for `texture`: it consumes a `mesh3d` wire and outputs `mesh3d`; the prompt is a node-local literal, not a wire)
- `src/lib/workflow/task-map.ts` (`texture` -> `texture_3d`)
- `src/lib/workflow/executor.ts` (`enqueueNode` / `resolveNodeInputs`: confirm the resolved inputs object is passed through to the job input unchanged, so a `texturePrompt` key reaches `Texture3DJobInputSchema`)
- `src/lib/workflow/authoring.spec.ts` (the existing assemble tests, to match the test pattern)

## Definition of done

1. Make `texture` a prompt-ALLOWING task (optional prompt), not a prompt-requiring one: `taskAllowsPrompt('texture')` is true, `taskRequiresPrompt('texture')` stays false (a texture op can run from just an upstream mesh with no prompt).
2. In BOTH `assembleDefinition` and `buildSingleNodeDefinition`, when a `texture` node has a non-empty prompt, emit it as a `literal` binding under the input key **`texturePrompt`** (NOT `prompt`), so it validates against `Texture3DJobInputSchema`. The existing mesh wire (`parentAssetId`) is unchanged.
3. Confirm the resolved input reaches the `texture_3d` job: trace `enqueueNode` -> the job `input` -> `Texture3DJobInputSchema.parse`. If the schema rejects an unknown `texturePrompt`, fix the binding key to match the schema's actual field name (read the schema, do not guess).
4. Tests in `authoring.spec.ts`: (a) a texture node WITH a prompt assembles to a definition whose texture node carries `inputs.texturePrompt = { kind: 'literal', value: <text> }`; (b) a texture node with NO prompt still assembles and runs (no error, no empty prompt emitted); (c) the single-node path (`buildSingleNodeDefinition`) matches.
5. If the node card UI needs a label/placeholder tweak so a texture node's prompt textarea reads as "texture prompt (optional)", make that minimal change in the node card; do not redesign the card.

Plus, always:
- the `verify` gate passes
- single conventional commit describing the WHY (texture prompt was dropped; now mapped to `texturePrompt`)

## Constraints

- Do NOT change the frozen `advanceWorkflow` readiness/finalize math in `executor.ts`.
- Avoid touching the published `@marlinjai/studio-core` workflow SCHEMA (`packages/lumitra-core/src/workflow/types.ts`) unless strictly required; this is an app-side authoring fix. If you must, rebuild the package (the verify gate already does).
- No em-dashes or en-dashes in any new comment or string.
- Stay in this worktree. Do not push or merge.
- When done, output a final message that the task is complete.
