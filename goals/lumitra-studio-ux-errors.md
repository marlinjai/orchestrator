---
task: lumitra-studio-ux-errors
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-ux-builder, lumitra-studio-ux-home, lumitra-studio-ux-review]
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

UX wave U4: one structured error surface everywhere (audit item 4). Raw
provider strings ("KIE-Claude failed: 500: {json}") currently render verbatim.

- A single `ErrorBlock` component: alert icon, humanized TITLE mapped from
  known failure classes (a pure `humanizeStudioError(message)` classifier:
  provider 5xx/timeouts -> "The image/text service had a hiccup"; rate limits
  -> "Too many requests at once"; auth -> "You do not have access"; unknown ->
  generic), the raw detail behind a "Details" disclosure (never lost), and an
  optional Retry button wired by the caller.
- Adopt it at every user-facing error site: campaigns builder + scenario
  panel, review grid, try-on bench, mint flow, wardrobe normalizer, product /
  location mint and import surfaces. Remove the raw-string renderings.
- Classifier unit tests (each class + unknown fallback + detail preservation);
  component spec (retry seam, disclosure); per-surface spot specs updated
  mechanically, assertions not weakened (they now match the humanized title
  and can still assert the preserved detail).

## Constraints

Depends on U1/U2/U5 to avoid file collisions. Design law (rejected-red axis
for the block), seams, full verify chain incl. next build.
