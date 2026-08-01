---
task: lumitra-studio-ux-home
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

UX wave U2: a dashboard HOME plus a spend ledger (audit items 2 + 8).

- `/` becomes a dashboard (the chat surface moves to `/chat`, nav item renamed
  "Chat"; every existing deep link and the auth redirect keep working via a
  permanent redirect from old paths if any exist). Dashboard shows: a "Start a
  campaign" hero action; recent campaigns as thumbnail cards (cover = first
  approved or first shot image) linking to their records; compact counts
  (characters, products, locations, assets) linking to rosters; and the spend
  summary (below).
- Spend ledger: a pure server read model summing Job.costUsd over time windows
  (today / 7 days / 30 days), exposed via a guarded GET route; a small mono
  spend indicator in the nav (current 7-day total) opening a drawer with the
  windows and a recent paid-actions list (job kind, model, cost, when). No new
  schema: Job rows already carry costUsd.
- DB-backed read-model spec (windowing, empty case), route spec, dashboard and
  drawer component specs (seamed fetches).

## Constraints

Design law, boundary law, no new deps, seams, full verify chain incl. next
build. Do not modify the campaigns builder (a parallel slice owns it).
