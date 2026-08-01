---
task: lumitra-studio-ux-polish
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-ux-locations-picker, lumitra-studio-ux-errors]
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

UX wave U6, the global finishing pass (audit items 9 + 10 + typography/a11y
floors).

- ACTION color split: introduce an `action` token (a restrained blue, distinct
  from identity cyan `#6FD3E8`; pick a value that passes 4.5:1 on surface for
  text and reads clearly as interactive). Primary buttons and links move to
  `action`; identity cyan remains EXCLUSIVELY the frozen/locked identity axis
  (pills, reference borders, lock icons). Approval axis untouched. Update the
  design-law comment blocks that document the axes.
- Motion system (functional only): skeleton shimmer components for roster and
  grid loads (replacing blank/spinner panes), 200ms ease-out crossfade on
  generation-tile status changes, subtle slide-out on review approve/reject,
  and a cost-bar tick transition when the total changes. Respect
  prefers-reduced-motion (media query disables all of it).
- Typography/a11y floors: page titles to 28px; a 15-16px semibold section
  heading level used across surfaces; caps-mono micro-text floor 12px with one
  ink step up on dark surfaces; 44px minimum touch targets on interactive
  chips and filmstrip thumbnails.
- Specs: token presence + component variant tests updated; reduced-motion
  spec; a contrast unit check for the new action token values (pure).

## Constraints

Runs LAST (depends_on both remaining slices) because it touches shared
primitives (Button, tokens, tiles). Behavior byte-compatible: visual only.
Design law, seams, full verify chain incl. next build.
