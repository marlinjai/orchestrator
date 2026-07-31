---
task: lumitra-studio-campaign-canvas-finish
spec: docs/specs/2026-08-01-campaign-canvas-handover.md
shared_state: []
depends_on: []
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

FINISH the campaign-canvas slice on the EXISTING branch `orchestrator/campaign-canvas`
(worktree already contains the delivered core: pure builder, round-trip contract
test, re-cast rebinding helper, saved-record open-as-workflow). The operator has
DECIDED the escalated tradeoff:

- The broad-blast-radius canvas `bakedInputs` preservation is DEFERRED to its own
  follow-up slice. Do NOT attempt it here.
- In exchange, lossy canvas re-runs are FORBIDDEN: they must FAIL LOUD. Add a
  guard: when the canvas assembles a definition containing campaign-baked
  generate-image nodes (nodes carrying baked-literal inputImages / campaign
  metadata), the run action for those nodes is blocked with a visible, specific
  message ("This shot's references were baked by the campaign builder; canvas
  re-runs of baked shots land in a follow-up. Run it from the campaign, or edit
  prompt/model and open again from the builder."). Detection helper is pure and
  unit-tested; the block is additive and touches ONLY the run-gating path, not
  assembleDefinition itself. Executor-direct runs (the contract-tested path)
  stay exactly as delivered.

Then complete the two owed DoD items from the original goal:

1. Builder-path "Open as workflow" (pre-run): factor the shared prepare-shots
   logic out of the byte-compatible route, create the no-run Campaign record,
   bake, save, navigate: exactly like the saved-record path. UI state is
   testable with the repo's injected-seam component-test idiom (see
   TryOnBench / WardrobeNormalizer specs): "can't runtime-verify" is not a
   blocker for seamed specs.
2. The Re-cast picker UI wired to the delivered rebinding helper (character or
   location pick, preserved user edits asserted per the stateful-flow standard).

Everything else from goals/lumitra-studio-campaign-canvas.md still binds
(design law, boundary law, no new deps, seams, full verify chain incl.
`pnpm build`). Commit onto the existing branch; conventional lowercase subjects.
