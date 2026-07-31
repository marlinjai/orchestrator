---
task: lumitra-studio-roster-uniformity
spec: docs/plans/2026-07-20-character-frontend.md
shared_state: []
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

Make the character roster visually uniform: every portrait renders at the SAME
aspect ratio, and every character sheet is generated (and can be re-dressed)
to one wardrobe standard: a plain heather-gray crew-neck t-shirt. Today's
roster mixes crop ratios and wardrobe (some tees, some bare-shouldered), which
reads unprofessional.

## Read first

- `src/components/character/CharacterCard.tsx` + CharacterRoster (why do card
  portrait heights differ today? diagnose: the fix must make rendering uniform
  for ANY stored image ratio, not just future ones).
- `packages/lumitra-core/src/character/` sheetPrompts (seedFacePrompt,
  turnaroundViewPrompt) and their specs: the generation-side standard.
- The compose engine path (`src/lib/tryon/tryon.ts`, `/api/try-on` route) as
  the re-dress mechanism (NB2 edit on an existing reference).
- `~/software-dev/knowledge-base/standards/stateful-flow-testing.md`.

## Definition of done

- RENDER uniformity: roster cards and dossier reference tiles enforce a fixed
  portrait frame (object-cover crop) for any source ratio; no card is taller
  than its row siblings regardless of stored image dimensions. Spec asserts the
  class contract.
- GENERATION standard: seedFacePrompt and every turnaroundViewPrompt mandate
  "wearing a plain heather-gray crew-neck t-shirt" (full-body: adds plain dark
  straight-leg trousers) and standardized framing (seed/face/lighting views:
  head-and-shoulders, 1:1; three-quarter/profile: chest-up, 1:1; full-body:
  3:4). Thread aspectRatio through the sheet nodes' generate_image inputs
  (the schema already accepts aspectRatio). Prompt specs updated; the sheet's
  schema-parity specs keep passing.
- RE-DRESS tool: on the character dossier, a "Normalize wardrobe" action:
  for each reference whose image predates the standard, one NB2 edit
  ($0.08/image, catalog-priced, shown in mono BEFORE running) re-renders that
  reference to the standard (same category, same identity: prompt pins
  identity exactly like compose does). Results appear in a REVIEW grid
  (approval axis): only explicitly approved results REPLACE the stored
  reference image (new Storage Brain file; old file id kept on the row in a
  `previousStorageFileId` column: add via handcrafted migration: so one-step
  revert is possible via a "Revert" action per reference). Rejected results
  are discarded. Server runner in a server-only module (C4 lesson: never
  import the studio-core barrel from client-imported modules).
- Tests: card uniformity spec, prompt standard specs, re-dress flow specs
  (seamed model call: run/review/approve-replaces/reject-discards/revert),
  DB-backed replace + revert route specs, stateful-flow paths for the review
  flow (backtrack = re-run a single reference, resume after reload shows
  pending results, re-entry after completion starts clean).
- Full verify chain green incl. `pnpm build`.

## Constraints (hard, do not violate)

- NEVER auto-replace a frozen reference: replacement only via the explicit
  per-reference approval in the review grid. No batch auto-apply.
- No schema changes beyond `previousStorageFileId` on CharacterReference.
- Design law; no new dependencies; isolate:false seams.
