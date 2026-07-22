---
task: lumitra-studio-frontend-character-chip
spec: docs/specs/2026-07-20-frontend-character-chip.md
shared_state: [app-shell]
depends_on: [lumitra-studio-frontend-tokens]
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

Implement F3, the missing E2 surface and the highest payoff slice: a
CharacterChip in the chat composer that makes `characterSlug` visible,
pickable (frozen characters only; drafts disabled with the reason) and
revocable, persists like brand settings, honors `/?character={slug}`
preselection, and shows the mono budget readout ("identity refs take
priority: {n} of {maxInputImages} slots") when brand and character are both
active. Wire the slug into the existing generate request assembly. Per
decision D2, `NodeSettingsPanel` reuses the SAME chip component for
`characterSlug` node params on the curated character workflows. Hard
regression oracle: with no character selected, brand-only behavior is
byte-identical to today.

## Read first

- The spec at `docs/specs/2026-07-20-frontend-character-chip.md` IN FULL, including its Read first
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

- `shared_state: [app-shell]` with the nav-roster task; serialize.
- Display only on the budget: `allocateReferenceBudget` on the server stays
  the source of truth; do not reimplement allocation client-side.
