---
task: lumitra-studio-ux-review
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

UX wave U5: the campaign review grid becomes a real judging surface (audit
item 6).

- Lightbox: click any shot for full-resolution view (the existing
  NodeResultLightbox idiom; reuse it or extend it), with keyboard navigation
  (arrows between shots, A approve, R reject, Esc close) and the approve/
  reject actions inside the lightbox.
- Batch actions: "Approve all remaining" (with count + a confirmation stating
  lineage will be written) and per-shot Download; an "Export approved" action
  downloads approved shots (individual files; no zip dependency: sequential
  anchor downloads are fine, document the choice).
- Compare: select two shots -> side-by-side compare view inside the lightbox.
- aria-live="polite" on the grid's async status region; status text labels on
  every tile state (READY/RUNNING/FAILED already textual: keep).
- Component specs for lightbox nav, keyboard actions, batch approve
  (seamed approve fn), compare selection; stateful paths (reject inside
  lightbox returns to grid coherently; re-entering a finished campaign shows
  verdicts read-only as today).

## Constraints

Only review-surface files (components/campaigns review + lightbox lib);
do not touch the builder. Design law, seams, full verify chain.
