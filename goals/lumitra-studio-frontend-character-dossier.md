---
task: lumitra-studio-frontend-character-dossier
spec: docs/specs/2026-07-20-frontend-character-dossier.md
shared_state: []
depends_on: [lumitra-studio-frontend-nav-roster]
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

Implement F2: the `/characters/[slug]` dossier. Two-column layout: left
portrait plus mono key-value identity block (slug, refs, default model,
shot count, created); right frozen-reference grid with category captions,
the descriptor prompt as a read-only "locked at freeze" block, and the
recent-shots lineage grid with approved Pills. Header: breadcrumb, status
Pill, and ONE action ("Generate with {name}" linking to
`/?character={slug}`). A shots read path may be added as
`GET /api/characters/[slug]/shots` mirroring existing GET patterns if none
exists. Not-found and empty states are part of done.

## Read first

- The spec at `docs/specs/2026-07-20-frontend-character-dossier.md` IN FULL, including its Read first
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

- Do NOT add try-on or animate buttons; those tasks add their own entry
  points when their targets exist (they carry the `character-dossier` tag).
