---
task: lumitra-studio-campaigns-product-entity
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: [prisma, migrations, lockfile]
depends_on: []
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

Implement slice C0 of the Campaigns plan (`docs/plans/2026-07-24-campaigns-ai-studio.md`,
status decided, on main): Products as first-class entities.

## Read first

- The plan IN FULL: its Positioning, Decisions, and the C0 section are binding.
- `prisma/schema.prisma` Character + CharacterReference (the model to mirror).
- `src/lib/character/repository.ts`, `roster.ts`, `dossier.ts`, `tags.ts` (idioms to reuse).
- `src/components/character/` CharacterCard / CharacterTagsEditor / DeleteCharacterButton
  (component idioms), `src/components/ImageDropzone.tsx` + `src/lib/images/` (intake).
- `~/software-dev/knowledge-base/standards/stateful-flow-testing.md` (the mint wizard
  is a stateful flow; all four paths are required).

## Definition of done

- Prisma: `Product` (id uuid, slug unique, name, kind string "garment"|"accessory"|"prop",
  notes String?, tags String[] default [], createdAt/updatedAt) and `ProductReference`
  (id, productId cascade, storageFileId?, url?, label?, sortOrder, role string
  "main"|"detail"|"scale"|"isolated", createdAt) plus an `AssetProduct` join table
  (assetId, productId, unique pair, both cascade). HANDCRAFT the migration folder
  (timestamped dir + migration.sql, matching e.g. 20260724120000_character_tags):
  `prisma migrate dev` will demand a local reset; do NOT reset any database.
- Repository + API: CRUD mirroring characters: POST/GET list `/api/products`,
  GET/PATCH/DELETE `/api/products/[slug]` (guardMutation "studio.character.write" idiom;
  PATCH accepts name/notes/kind/tags with the character tags normalizer reused or
  generalized), reference upload endpoint mirroring character references, all behind
  the same auth guards as their character siblings.
- Mint flow `/products/new`: name -> slug (immutable, auto-derived), kind picker,
  1-4 photos via ALL intake paths (file, cross-site drag, Cmd+V paste, asset picker,
  server-side URL import via POST /api/images/import). AUTO-FREEZE on create: no QC
  gate; references stay editable on the dossier afterwards. Per-photo optional
  "Isolate" action running catalog model `fal/birefnet-v2-background-remove` and storing
  the result as a `role: "isolated"` reference. `kind: "accessory"` shows a
  pending-amber nudge asking for one worn/held photo saved with `role: "scale"`.
- Roster `/products` (cards with portrait, kind, tags chips) + dossier
  `/products/[slug]` (references grid with add/remove/re-order, tag editor, delete
  with in-app confirmation dialog, danger variant). Nav gains a Products item.
- Tests: DB-backed route specs (create, patch incl. tags, delete detaches AssetProduct
  rows but keeps assets, 404s, auth-rejected), mint wizard component specs covering
  forward + backtrack-and-revise + resume + re-entry, isolate-action spec with an
  injected seam (no real fal call), roster/dossier specs. Schema-parity where a
  payload meets a Zod schema.
- Full verify chain green; conventional commits (lowercase subjects).

## Constraints (hard, do not violate)

- Design law from `docs/plans/2026-07-20-character-frontend.md`: tokens, two-color-axis
  rule (identity cyan never marks approval), Geist Mono for machine values.
- Do not modify the Character models or flows except to extract genuinely shared
  helpers (e.g. generalizing the tags normalizer); no behavior change to characters.
- No new dependencies. Never run `prisma migrate reset` or `prisma migrate dev`
  against any database. Suite runs `isolate: false`: no module-level vi.mock of
  shared modules; use injected seams.
- Single-purpose branch; do not touch files outside this slice's scope.
