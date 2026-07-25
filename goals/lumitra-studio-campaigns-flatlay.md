---
task: lumitra-studio-campaigns-flatlay
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-campaigns-surface]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

Implement slice C4 of the Campaigns plan: the flat-lay fast path on `/campaigns`.

## Read first

- The plan IN FULL (C4 and the Positioning section's Kive mechanics).
- C3's `/campaigns` builder and allocator; the garment intake set
  (`src/components/ImageDropzone.tsx`, `src/lib/images/`), and the isolate action
  from C0's product mint.

## Definition of done

- Direct mode: the product-pick step offers a "Flat-lay" slot alternative: drop /
  paste / import ONE outfit flat-lay image used AS-IS as a single reference
  occupying one product slot (label "flat-lay outfit" in the prompt: the composer
  from C1 gains a variant clause instructing the model to dress the character in
  ALL items of that flat-lay). Zero entity setup; works alongside 0..3 real
  products within the same 8-slot budget.
- Split mode: a "Split into products" action on a dropped flat-lay: one
  `fal/nano-banana-2-edit` call PER detected item is out of scope for detection;
  instead the user draws no boxes: the action runs a single edit call per item
  the user names in a lightweight list UI (add item name + kind rows), each call
  isolating that named item onto a clean background (prompt template tested),
  producing quick-mint Product cards (name + kind prefilled, auto-freeze on
  confirm, reference role "isolated"). Cost per item shown in mono before running.
- Stateful-flow tests: flat-lay slot swap invalidates allocation-derived cost;
  removing the flat-lay restores product slots; split-mode list backtrack (rename
  or remove an item before running) never spends; resume after reload keeps the
  campaign draft coherent.
- Allocator + prompt tests extended for the flat-lay slot; full verify chain
  green; conventional commits.

## Constraints (hard, do not violate)

- No auto-detection ML, no new dependencies, no FASHN.
- Isolate calls only through injected seams in tests: no real spend.
