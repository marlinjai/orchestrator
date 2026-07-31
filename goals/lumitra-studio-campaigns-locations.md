---
task: lumitra-studio-campaigns-locations
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: [prisma, migrations, lockfile]
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

Extend Campaigns with LOCATIONS: real places (retreat villas, chalets) whose
photos condition the shot so a character can be placed INTO the venue for
marketing editorial content. This is the platform's original use case: "we only
have pictures of the places; we want marketing content with models inside them."

## Read first

- `docs/plans/2026-07-24-campaigns-ai-studio.md` (the campaigns architecture this
  extends) and the C2/C3 modules: `src/lib/campaigns/brandStudio.ts`,
  `listStudios.ts`, `allocateCampaignReferences.ts`, `campaignPrompt.ts`,
  `campaignBatch.ts`. Brand studios are the exact pattern to mirror: a location
  is "a studio whose scene comes from reference images".
- The Product entity (schema + repository + roster/dossier) as the entity idiom.
- `src/lib/campaigns/flatLaySplitServer.ts` header comment: NEVER import the
  `@marlinjai/studio-core` barrel from a module any client component imports
  (it broke the C4 deploy). Server runners live in server-only modules.

## Definition of done

- Schema: `Location` (id, slug unique, name, region String?, notes String?,
  tags String[] default [], createdAt/updatedAt) + `LocationReference`
  (locationId cascade, storageFileId?, url?, label?, sortOrder, createdAt).
  HANDCRAFTED migration folder; never `prisma migrate dev`/`reset` against a DB.
- Entity surfaces mirroring products: guarded CRUD (`studio.location.write`
  registered in `src/lib/auth/permissions.ts` requiring `tenant.member`),
  reference upload, `/locations` roster (cards show a cover photo, region, tag
  chips), `/locations/[slug]` dossier (references grid, tag editor, delete with
  confirmation). Mint at `/locations/new`: name/slug/region/notes + 1-8 photos
  via the full intake set; auto-freeze; references editable after.
- BULK IMPORT endpoint `POST /api/locations/import` (same guard): accepts
  `{ name, slug?, region?, notes?, images: dataUrl[] }`, creates the location +
  references (Storage Brain mirror path like other uploads), idempotent per slug
  (re-import updates metadata, appends only new images by content hash or
  index-label). DB-backed spec incl. idempotency.
- Location studios: `locationStudio.ts` mirroring brandStudio: id
  `location:<slug>`, scene template built from region/notes ("editorial
  photograph of the person AT the location shown in the location references,
  authentic architecture, furnishings and light of the venue"), refs capped at
  2 in the standard budget. `listStudios` gains a "Locations" group (locations
  without references excluded).
- Allocator: location refs occupy the same conditioned-scene slot class as
  brand refs (a campaign uses a brand studio OR a location studio, never both
  simultaneously in v1: the selector enforces single choice). Extend allocator +
  its tests for the location case; overflow order unchanged (scene refs drop
  before product/character refs).
- Prompt: buildCampaignPrompt names the location reference positions and pins
  scene fidelity ("keep the real venue's architecture, materials and view;
  do not invent a different interior"). Contract tests for 1/2 location refs.
- Campaigns builder: studio selector shows the three groups; picking a location
  studio shows its cover thumbnail. Stateful-flow paths re-verified (changing
  studio between brand/location re-allocates and updates cost).
- Full verify chain green (NOTE: the chain now includes `pnpm build`: Next
  production build; client/server boundary discipline is verified, not assumed).

## Constraints (hard, do not violate)

- Design law (tokens, axes, mono). No new dependencies. isolate:false seams.
- Do not modify products/characters beyond genuinely shared helper extraction.
