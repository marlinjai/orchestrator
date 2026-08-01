---
task: lumitra-studio-ux-locations-picker
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-ux-builder]
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

UX wave U3: the studio/scene selector deserves the venues' photography
(audit items 3 + 7).

- In the reworked builder's Studio step: the 10 library presets stay compact
  chips; LOCATIONS become image cards (cover photo, name, region) in a
  scrollable grid with a search input filtering by name/region, and country
  grouping headers. Brand studios keep their group.
- Smart covers everywhere a location cover renders (picker, roster, dossier,
  dashboard): a pure `pickLocationCover(references)` that prefers landscape-
  orientation images (width>height when dimensions are known) and skips
  obvious non-establishing shots when metadata allows, falling back to the
  first reference; a location dossier gains an explicit "Set as cover" action
  per reference (persisted via a `coverReferenceId` column: handcrafted
  migration: which, when set, wins over the heuristic).
- Specs: cover heuristic unit tests, set-as-cover route + persistence
  (DB-backed), picker search/filter component tests.

## Constraints

Builds ON the U1 builder structure (depends_on). Design law, seams, full
verify chain incl. next build.
