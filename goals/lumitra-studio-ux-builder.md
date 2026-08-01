---
task: lumitra-studio-ux-builder
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
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

UX wave U1: rework the /campaigns builder from a scroll marathon into a guided
bench (audit items 1 + 5). The single page currently stacks six full-height
sections and renders the FULL character roster twice (primary + second
character). Rework:

- Progressive disclosure: each step (Character, Products, Studio/Scene, Shot
  ideas, Shots) collapses to a compact summary chip once satisfied (selected
  character avatar + name; product count; venue name + thumbnail) with a
  "Change" affordance re-expanding it. Exactly ONE step expanded at a time by
  default; explicit expand of others allowed. The mint flow's Stepper idiom is
  the model.
- Character pickers: compact horizontally scrollable avatar rows (44px+ targets)
  with a "Show all" expansion; NEVER two simultaneous full-roster grids. The
  second-character picker excludes the already-picked primary.
- Sticky bottom bar, always visible: itemized-on-hover total cost (mono),
  slot-budget readout, and the Generate button; disabled-state reasons surface
  in the bar. "Open as workflow" moves here as a visible secondary button.
- Two-column bench on >=1280px: configuration left; a live summary column right
  (chosen character portrait, venue cover, selected scenario titles, running
  cost). Single column below 1280px.
- Preserve every existing behavior byte-for-byte at the API/request layer:
  this is layout/disclosure only; the existing builder specs keep passing with
  minimal, mechanical updates (interaction paths may change: update
  respectfully, never weaken assertions).
- Stateful-flow paths re-verified after the rework (collapse/expand is UI
  state: reload restores selections as today).

## Constraints

Design law (tokens, axes, mono), boundary law, no new deps, isolate:false
seams, full verify chain incl. next build.
