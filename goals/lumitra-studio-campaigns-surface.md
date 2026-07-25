---
task: lumitra-studio-campaigns-surface
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: [prisma, migrations, lockfile]
depends_on: [lumitra-studio-campaigns-product-entity, lumitra-studio-campaigns-studio-library, lumitra-studio-campaigns-brand-studios]
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

Implement slice C3 of the Campaigns plan: the `/campaigns` surface: pick one
character, up to 4 products, a studio, a shot count, batch-generate, review.

## Read first

- The plan IN FULL: C3's reference-budget allocator rules are the hard kernel.
- `src/lib/character/allocateReferenceBudget.ts` + spec (the allocator to extend),
  `src/lib/character/referenceBudget.ts`.
- C1/C2 modules (`studios.ts`, `campaignPrompt.ts`, `brandStudio.ts`, `listStudios.ts`).
- The compose submission path (`src/lib/tryon/tryon.ts`, `/api/try-on` route) and
  the F6 shot-review component idiom (`src/components/character/` shot review).
- `~/software-dev/knowledge-base/standards/stateful-flow-testing.md`: the campaign
  builder is a stateful flow; all four paths required.

## Definition of done

- Schema: `Campaign` (id, name, characterId SetNull?, studioId string, paramsJson,
  createdAt) and `CampaignShot` (id, campaignId cascade, jobId?, assetId SetNull?,
  status, sortOrder). HANDCRAFT the migration folder; never migrate reset/dev
  against a database. AssetProduct lineage rows are written for approved shots.
- Pure allocator `allocateCampaignReferences` in `src/lib/campaigns/`: total slots
  = catalog maxInputImages for `fal/nano-banana-2-edit` (8, read from the catalog,
  never retyped): character face + full-body ALWAYS reserved (2), one primary ref
  per product (up to 4), brand refs up to 2 only when the studio is a brand studio;
  unused product slots redistribute to extra product detail refs (role "detail",
  then "isolated"); overflow drops brand refs first, then detail refs, NEVER the
  character pair or a product's primary ref. Exhaustive unit tests incl. 0..4
  products x library/brand studio x missing-reference edge cases.
- `/campaigns` page: character picker (roster with tag filter), product multi-pick
  (max 4, roster with tag filter), studio selector (Library / Your brands groups),
  shot count 1-8, optional variation input (reject > 2 words inline), mono cost
  line N x catalog price BEFORE the run. Nav gains Campaigns.
- Batch: N generate_image jobs (provider fal, model fal/nano-banana-2-edit,
  inputImages from the allocator with positions matching the prompt, prompt from
  buildCampaignPrompt with a per-shot variation clause), Campaign + CampaignShot
  rows created first, jobs polled into a live grid.
- Review: approve/reject per shot (approval color axis, never identity cyan);
  approve writes the Asset lineage (characterId, AssetProduct rows, campaign
  linkage); reject hides from the grid but deletes nothing. Campaign list page
  (`/campaigns` shows recent campaigns; re-entering one shows its shots and
  statuses: resume path).
- Stateful-flow tests: forward, backtrack (change product set after selecting
  studio: derived cost + allocation update; change character: allocation redone),
  resume (reload mid-batch re-attaches via Campaign rows), re-entry (a finished
  campaign re-entered read-only; a new campaign starts clean).
- API routes guarded like siblings ("studio.generate" for run, character-write
  idiom for mutations); DB-backed route specs; allocator schema-parity test
  (composed payload passes GenerateImageJobInputSchema).
- Full verify chain green; conventional commits.

## Constraints (hard, do not violate)

- v1 is SINGLE character per campaign. No FASHN anywhere in this surface.
- Design law: tokens, two color axes, mono machine values. No new dependencies.
- isolate:false suite: injected seams, no module-level vi.mock of shared modules.
