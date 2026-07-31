---
task: lumitra-studio-campaign-scenarios
spec: docs/plans/2026-07-24-campaigns-ai-studio.md
shared_state: []
depends_on: [lumitra-studio-campaigns-locations]
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

Campaign SCENARIOS: from a chosen location (and its photos) plus the selected
character(s), generate an exhaustive, EDITABLE shot list of editorial scenarios
("cooking fresh fruits and vegetables in the kitchen", "yoga at sunrise in the
garden", "swimming in the pool", "aperitivo on the terrace", "reading in the
window seat"...), each scenario becoming one per-shot prompt the user can
freely customize before the paid run. Also: scenario shots may include UP TO
TWO characters (the "models cooking together" case): the first relaxation of
the v1 single-character rule.

## Read first

- `docs/plans/2026-07-24-campaigns-ai-studio.md` + the campaigns modules
  (campaignPrompt, campaignBatch, allocateCampaignReferences, listStudios,
  locationStudio from the locations slice, loadCampaign, the /campaigns pages).
- The vision task path (B4): image-to-text captioning via the existing
  provider/task machinery (florence-2 / moondream in the catalog) and how the
  executor runs `image-to-text` jobs.
- The LLM director text task (B3) and its provider path: how a text job is
  created and polled.
- `flatLaySplitServer.ts` header (client/server boundary law) and
  `~/software-dev/knowledge-base/standards/stateful-flow-testing.md`.

## Definition of done

- **Amenity analysis** (server): `analyzeLocationAmenities` runs image-to-text
  captioning over a location's references (one job per photo, catalog-priced,
  results cached on the Location row: add a `amenitiesJson` column via
  handcrafted migration with analyzed-at + per-photo captions + a derived
  amenity tag list). Guarded route `POST /api/locations/[slug]/analyze`; cost
  shown in mono before running; idempotent (re-analyze replaces).
- **Scenario generation** (server): `generateShotScenarios` composes a text-task
  prompt from the location (name, region, notes, amenity tags, captions) + the
  selected characters (names + locked descriptors) + optional user direction
  ("more wellness", "food focused") and returns 8-16 DIVERSE scenarios as
  structured JSON (id, title, sceneClause, activityClause, charactersInvolved,
  suggestedTimeOfDay). Validated by Zod; malformed LLM output retries once then
  errors visibly. Unit-tested via an injected text-task seam.
- **Builder integration**: a "Shot ideas" panel on /campaigns once a location
  studio + characters are chosen: Generate button (mono cost for the text call),
  scenario cards with checkbox + EDITABLE prompt text (the composed per-shot
  clause, free-text editable: this supersedes the two-word variation cap for
  scenario shots; the plain variation path remains for non-scenario runs),
  selected scenarios become the batch (shot count = selected count, each shot
  uses its scenario clause in buildCampaignPrompt).
- **Two characters**: the builder allows selecting a SECOND character for
  scenario runs. Allocator extension: each character reserves face+full-body
  (2x2=4 slots), location refs up to 2, remaining slots to products; overflow
  drops products first here (scenario shots are about people in the place),
  documented + exhaustively tested. Prompt names both identities and their
  reference positions; contract tests cover 1 and 2 characters.
- **Plan doc**: update `docs/plans/2026-07-24-campaigns-ai-studio.md`: move
  multi-character from "Out of scope" to a "Shipped in scenarios (max 2)" note
  and document the scenario layer, same commit series.
- Stateful-flow paths: regenerating scenarios replaces unselected cards but
  PRESERVES user-edited selected ones (edits are user work); changing location
  or characters invalidates the scenario list (derived state, keyed); resume
  mid-batch re-attaches; re-entry clean.
- Full verify chain green incl. `pnpm build`.

## Constraints (hard, do not violate)

- LLM + vision calls only through injected seams in tests; no real spend.
- Client/server boundary law; design law; no new dependencies.
- The non-scenario campaign path (studio presets, 2-word variation) stays
  byte-compatible.
