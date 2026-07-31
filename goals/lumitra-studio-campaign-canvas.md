---
task: lumitra-studio-campaign-canvas
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-campaign-scenarios]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint && pnpm build
verify_fix_cap: 2
verify_timeout_s: 2400
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

Make the campaign pipeline FULLY CUSTOMIZABLE: any configured campaign
(character(s), products, location/studio, scenario shots) can be opened as an
editable workflow on the existing canvas, modified node-by-node (prompts,
models, extra processing nodes), saved as a reusable custom pipeline, and run
through the existing workflow machinery: the guided /campaigns builder is the
golden path, the canvas is the power path, and they produce identical results
for an unmodified pipeline.

## Read first

- `src/lib/workflow/` (curated definitions, executor, authoring, saved-store,
  EditableWorkflowCanvas usage) and the character sheet's
  `bakeCharacterSheetPrompts` open-in-canvas pattern.
- The campaigns modules incl. the scenarios slice (campaignBatch, per-shot
  clauses, allocator) and `/api/v1/workflows` run/save routes.
- The client/server boundary law and the stateful-flow standard.

## Definition of done

- Pure `buildCampaignWorkflowDefinition(params) -> WorkflowDefinition`: one
  `generate_image` node per shot (model per node from the campaign's model, so
  a node can be individually switched later; prompt baked as a literal from
  buildCampaignPrompt incl. the shot's scenario clause; inputImages baked as
  literal url arrays from the allocator, order matching the prompt's reference
  positions). Round-trip contract test: running the unmodified definition
  through resolveNodeInputs + GenerateImageJobInputSchema equals the builder's
  own job payloads shot-for-shot.
- "Open as workflow" on a configured campaign (builder) AND on a saved
  Campaign record: bakes the definition, saves it via the existing saved-
  workflow store (named "Campaign: <name>"), navigates to the canvas. Edits
  there are ordinary workflow edits (models switchable per node, prompts
  editable, nodes addable e.g. upscale / background-remove chained on a shot's
  output: document one worked example in the canvas empty-state help).
- Runs from the canvas keep asset lineage when nodes carry the campaign
  metadata (bake a `campaignId` into the definition's metadata; the executor
  path tags produced assets' lineage exactly like builder runs; a definition
  stripped of the metadata runs as a plain workflow: no crash, no fake
  lineage).
- Re-run with swapped subjects: a saved campaign pipeline exposes "Re-cast":
  pick a different character (or location) and the baked literals for that
  subject's reference positions + identity clauses are re-derived (pure
  rebinding helper, unit-tested; user-edited prompt text outside the identity/
  reference clauses is PRESERVED: derived-state keying per the standard).
- Stateful-flow paths for open -> edit -> run -> re-cast; full verify chain
  green incl. `pnpm build`.

## Constraints (hard, do not violate)

- No engine changes beyond what exists (definitions, saved store, executor);
  no new dependencies; boundary + design law; seams in tests.
- The guided builder's behavior stays byte-compatible when the canvas is not
  used.
