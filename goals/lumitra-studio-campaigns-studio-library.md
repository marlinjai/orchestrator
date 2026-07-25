---
task: lumitra-studio-campaigns-studio-library
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-campaigns-product-entity]
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

Implement slice C1 of the Campaigns plan (`docs/plans/2026-07-24-campaigns-ai-studio.md`):
the curated Studio preset library as versioned data.

## Read first

- The plan IN FULL (C1 + the C3 section it feeds: the template contract must
  compose with a character descriptor + product list + shot variation clause).
- `src/lib/tryon/composePrompt.ts` + its spec (the prompt-contract idiom to follow).
- `src/lib/workflow/curated.ts` (how versioned in-repo registries are structured).

## Definition of done

- `src/lib/campaigns/studios.ts`: a typed, versioned registry of StudioPreset
  entries: { id, label, family ("studio"|"street"|"nature"|"flat-lay"|"night"|
  "luxury"), promptTemplate, negativePrompt?, composition and lighting clauses,
  aspectRatio, thumbnailAssetId: string | null }. Exactly these 10 v1 presets:
  White Studio, Editorial Portrait, Golden Hour Street, Soho Streetstyle, Beach,
  Alpine, Cornfield, Flat-lay Top-down, Night Neon, Marble Luxury. Author each
  template with real photographic direction (lighting, lens feel, composition),
  not filler.
- A pure `buildCampaignPrompt(preset, { descriptor, products, variation })`
  composer in `src/lib/campaigns/campaignPrompt.ts`: mirrors composePrompt's
  image-order contract (person refs and product refs are named by position),
  pins identity exactly like compose mode does, names each product and its
  reference position, appends the preset's scene clauses, caps the free-text
  variation at two words' worth (longer input is rejected by the caller's
  validation, not silently truncated).
- Contract tests: every registry preset composes (with a fixture descriptor +
  1..4 products) into a prompt that passes GenerateImageJobInputSchema.safeParse
  when wrapped in a fixture generate_image payload; registry ids unique;
  template placeholders all consumed.
- Thumbnails: `thumbnailAssetId: null` for now with a `scripts/` one-shot
  generation script STUBBED as a documented TODO-free CLI (writes real thumbnails
  when run with credentials; do NOT run it in this slice, do not spend money).
- Full verify chain green; conventional commits.

## Constraints (hard, do not violate)

- Pure data + pure functions only: no DB schema, no API routes, no UI in this
  slice. No new dependencies. No fal calls in tests.
- Do not modify compose mode or the try-on bench.
