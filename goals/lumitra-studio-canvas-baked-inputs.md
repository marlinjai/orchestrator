---
task: lumitra-studio-canvas-baked-inputs
spec: docs/specs/2026-08-01-campaign-canvas-handover.md
shared_state: []
depends_on: [lumitra-studio-campaign-canvas-finish]
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

Close the deferred canvas gap: the canvas's `assembleDefinition` must PRESERVE
baked-literal `inputImages` and campaign metadata when re-assembling
generate-image nodes, so a canvas re-run of a campaign shot is byte-identical
to the builder's own job payload, and the loud guard added by the finish slice
can be REMOVED (replaced by real support). This touches the shared canvas
machinery every workflow uses: the whole slice is about doing that safely.

## Read first

- `docs/specs/2026-08-01-campaign-canvas-handover.md` (the Worker's own
  analysis and recommendation: additive `bakedInputs` preservation).
- The canvas assembly path (`assembleDefinition` and friends in
  `src/lib/workflow/`), the campaign-baked node detection helper from the
  finish slice, and campaignWorkflow.ts's round-trip contract test.

## Definition of done

- ADDITIVE preservation: nodes carrying baked-literal image inputs (or campaign
  metadata) round-trip through canvas assembly with those literals intact;
  wiring a NEW image source over a baked literal replaces it explicitly (user
  intent), never silently. Non-campaign workflows assemble byte-identically to
  today: a regression contract test asserts assembleDefinition output is
  unchanged for every existing curated definition and a corpus of saved-store
  fixtures.
- The loud run-guard from the finish slice is removed; its spec becomes the
  positive test: canvas re-run of a baked shot node produces a job payload
  byte-identical to the builder's (extend the existing round-trip contract).
- The canvas's image-wiring block for `image-edit` nodes is relaxed ONLY as far
  as baked literals require; document the decision in the module header.
- Stateful-flow paths: edit prompt then re-run keeps refs; re-cast then re-run
  uses the re-derived refs; full verify chain green incl. `pnpm build`.

## Constraints (hard, do not violate)

- No behavior change for non-campaign workflows (the regression contract is the
  gate). Design/boundary law, seams, no new deps.
