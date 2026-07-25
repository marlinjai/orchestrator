---
task: lumitra-studio-campaigns-brand-studios
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-campaigns-studio-library]
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

Implement slice C2 of the Campaigns plan: brand-conditioned Studios on the C1
template contract.

## Read first

- The plan IN FULL (C2, and C3's reference-budget rules: brand refs get AT MOST
  2 slots and only when a brand studio is active).
- `src/lib/campaigns/studios.ts` + `campaignPrompt.ts` from C1 (the contract).
- The brand system: `src/lib/brand/` (repository, config, modes, references)
  and how E2 injects brand references into generation.

## Definition of done

- `src/lib/campaigns/brandStudio.ts`: derive a StudioPreset-compatible entry
  from a brand: id `brand:<slug>`, label from the brand name, promptTemplate
  built from the brand's voice/mode text plus neutral studio scaffolding, and a
  `brandRefUrls: string[]` capped at 2 (selection order documented: primary
  mood/style references first). Pure; brand loading stays in the caller.
- A studios listing helper that merges "Library" (C1 registry) and "Your brands"
  (one entry per brand that has references), typed for the C3 selector:
  `listStudios(prisma)` in `src/lib/campaigns/listStudios.ts` with a DB-backed
  spec.
- `buildCampaignPrompt` composes brand studios exactly like library ones; brand
  reference positions are named in the prompt after product positions. Contract
  tests extended: a brand studio with 0/1/2 refs, and the no-references brand is
  EXCLUDED from the listing.
- Full verify chain green; conventional commits.

## Constraints (hard, do not violate)

- No schema changes. No UI in this slice. No new dependencies.
- Do not modify the C1 registry entries; extend types only compatibly.
