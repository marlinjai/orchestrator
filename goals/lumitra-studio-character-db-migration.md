---
task: lumitra-studio-character-db-migration
spec: docs/specs/2026-07-19-character-db-migration.md
shared_state: [prisma, migrations]
depends_on: []
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

DO NOT DISPATCH until the plan PR `marlinjai/lumitra-studio#83` has merged
(so `docs/specs/2026-07-19-character-db-migration.md` reads
`status: decided` on the default branch). The gating product decisions are
resolved (2026-07-20): Character is a project-independent library and
`Asset.characterId` is the only relation.

Implement the leaf spec at
`docs/specs/2026-07-19-character-db-migration.md` in full: add `Character`
and `CharacterReference` Prisma models (structural clone of `Brand`/
`BrandReference`), add `Asset.characterId`, a DB loader
(`src/lib/character/loadCharacterFromDb.ts`), a repository
(`src/lib/character/repository.ts`), and the `/api/characters*` routes. This
is the foundation slice every other Character Consistency Engine task
depends on (E1 and E2 in the parent plan).

## Read first

- The spec file in full (Definition of done items 1-8, and the Constraints
  section).
- `prisma/schema.prisma`: the `Brand` and `BrandReference` models, the exact
  structural template.
- `src/lib/brand/loadBrandFromDb.ts` and `src/lib/brand/repository.ts`: the
  loader/repository pattern to clone.
- `src/app/api/brands/route.ts` and its `[slug]` subroutes: the API route
  shapes to clone.
- `src/lib/asset/sign.ts` and `src/lib/storage/*`: the existing Storage
  Brain SDK/signing utility, reuse it, do not add a second storage client.
- `docs/specs/2026-06-01-brand-db-migration.md`: the prior slice that did
  this exact shape of migration for brands.
- The parent plan `docs/plans/2026-07-19-character-consistency-engine.md`
  for the full phase context (this is phase E0).

## Definition of done

Everything the spec's "Definition of done" section lists (Prisma models +
additive migration generated with `--create-only` against a local throwaway
DB, DB loader, repository, API routes, tests). Plus:

- `pnpm test`, `pnpm lint`, typecheck pass.
- Spec frontmatter already reads `decided`; if you find it still
  `proposed` when you start, stop and escalate
  rather than proceeding).
- Single commit, conventional message.

## Constraints

- **Do NOT apply the migration to any non-local database. Do NOT deploy.**
  `--create-only` against a local throwaway DB, then stop.
- **Do NOT touch `Brand`/`BrandReference` or `injectBrandReferences.ts`.**
  Purely additive; brand behavior must be byte-identical before/after.
- Stay in this worktree. Do not push to any remote.
- No em-dashes or en-dashes anywhere (repo style rule). Conventional commit.
- Report via `update_state`: `file_touched`, `decision` (the exact
  project-relation choice implemented, citing the plan doc's resolved
  option), `open_thread`, `commit`.

## Notes

- This task's spec is the dependency root for `lumitra-studio-character-
  sheet-workflow` (E1) and `lumitra-studio-character-injection` (E2).
  Neither should dispatch until this one's commit lands.
- Shares `prisma` + `migrations` state; the dispatcher must not run this
  concurrently with any other prisma-touching task.
