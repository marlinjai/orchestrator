---
task: lumitra-studio-frontend-nav-roster
spec: docs/specs/2026-07-20-frontend-nav-roster.md
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

Implement F1: promote Characters to a top-level destination. Real nav
tabs (Generate / Characters / Workflows / Assets) with active state and
icon-plus-label, replacing the ad hoc header links in `StudioApp.tsx`
(Shot Review leaves the header). Build `/characters`: the casting-card
roster grid (portrait from the first face reference, status Pill,
filmstrip of up to 4 reference thumbnails with identity-cyan borders when
frozen, name plus mono slug and ref count), server-fetched via
`listCharacters`, with skeleton loading and an empty state that leads to
`/characters/new`.

## Read first

- The spec at `docs/specs/2026-07-20-frontend-nav-roster.md` IN FULL, including its Read first
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

- `shared_state: [app-shell]` with the character-chip task: both edit
  StudioApp/ChatInterface territory; the dispatcher must serialize them.
- Cards link to `/characters/[slug]`, which lands with the dossier task;
  the two are chained by depends_on so the gap exists only between merges.
