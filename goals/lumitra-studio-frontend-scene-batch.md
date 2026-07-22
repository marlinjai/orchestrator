---
task: lumitra-studio-frontend-scene-batch
spec: docs/specs/2026-07-20-frontend-scene-batch.md
shared_state: []
depends_on: [lumitra-studio-frontend-nav-roster, lumitra-studio-frontend-character-chip, lumitra-studio-frontend-shot-review-recraft]
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

DO NOT DISPATCH until the plan PR `marlinjai/lumitra-studio#91` has merged, so the spec below reads `status: decided` on the default branch.

Implement F7, the campaign surface: `/characters/[slug]/scenes` places
one frozen character into many location photos in one deliberate
submission. Scene tray from AssetBrowser multi-select plus upload; shared
prompt template with helper text; candidates-per-scene; mandatory mono
pre-submission summary ("{scenes} scenes x {candidates} candidates, est.
{cost}"). Fans out one generate call per scene (bounded concurrency,
record the bound as a decision) with characterSlug, the scene image as a
direct input, and candidateCount; per-scene progress and retry; hands off
to `/shot-review` filtered to the character. Frontend composition over
E2 + E4: NO new backend primitives, no batch table, no new routes; if that
proves impossible, stop and escalate rather than widening the backend.

## Read first

- The spec at `docs/specs/2026-07-20-frontend-scene-batch.md` IN FULL, including its Read first
  list (those files are this task's required reading) and its Constraints.
- `docs/plans/2026-07-20-character-frontend.md`: the token table, the
  two-color-axis rule, the mono/sans typography rule, and decisions D1-D3
  are binding design law for every frontend slice.

## Definition of done

The spec's "Definition of done" list, in full, plus:

- `pnpm test`, `pnpm lint`, typecheck pass (the verify gate runs the full
  chain).
- Single conventional commit describing the WHY.

## Constraints (hard, do not violate)

- Implement the spec IN FULL, including its own Constraints block; the
  spec's constraints are part of this goal.
- The plan's design foundation is binding: consume the F0 tokens and
  primitives, Geist Mono for machine values, identity cyan only for
  frozen/locked, approval state on its own amber/green/red axis. No raw hex
  values, no `neutral-*` utilities, no emoji icons.
- Accessibility floor: visible focus states, aria-labels on icon-only
  controls, state as form plus color (never color alone), reduced motion
  respected.
- NO live provider calls in tests; mock jobs/providers.
- Do NOT touch prisma, migrations, or provider/server code unless the spec
  explicitly allows it.
- Stay in this worktree. Do not push to any remote. No destructive
  git/shell commands.
- No em-dashes or en-dashes anywhere (repo style rule). Conventional
  commit(s), single commit preferred.
- Report via `update_state`: `file_touched`, `decision`, `open_thread`,
  `commit`.

## Notes

- Batch grouping is by character plus submission time window client-side;
  durable named campaigns would be a separate backend spec, deliberately
  out of scope here.
