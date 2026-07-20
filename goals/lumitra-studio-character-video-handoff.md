---
task: lumitra-studio-character-video-handoff
spec: docs/specs/2026-07-19-character-video-handoff.md
shared_state: []
depends_on: [lumitra-studio-character-injection]
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

DO NOT DISPATCH until the spec's frontmatter reads `status: decided` AND
`lumitra-studio-character-injection` (E2) has merged (needs a character-
bound Image asset to animate). Does NOT depend on the QC-loop task (E4) at
the code level, even though animating only approved shots is the sane
workflow in practice. Implement the leaf spec at
`docs/specs/2026-07-19-character-video-handoff.md` in full: wire image-to-
video generation from an approved character-bound still using already-
catalogued fal models, and a HyperFrames export scaffold that packages the
resulting video Asset URL into a composition manifest.

## Read first

- The spec file in full, including the "Out of scope (E5b)" section, do
  not build multi-reference video binding, it is explicitly deferred.
- `packages/lumitra-core/src/models/catalog.ts`: confirm
  `fal/kling-v2-5-image-to-video` and `fal/seedance-pro-image-to-video`
  still exist and are wired (per the fal-multimodal-backbone plan's B1
  phase, already done as of this spec's writing, the codebase moves,
  re-verify before assuming).
- `src/lib/jobs/run-generation-job.ts`: the `kind === 'generate_video'`
  branch in `buildPlan`.
- `docs/specs/2026-06-16-fal-multimodal-backbone.md`: B1's webhook/async
  transport, the completion path for video jobs (NOT synchronous like
  image generation).
- `docs/plans/2026-06-07-lumitra-studio-composition-and-embed-architecture.md`:
  the embed contract: an embed consumes a RESULT (baked asset URLs), never
  the pipeline. The HyperFrames manifest follows this exactly.

## Definition of done

Everything the spec's "Definition of done" section lists: step 1 is a
verification (confirm the video path already works end-to-end for a
character-bound still, document the finding rather than writing speculative
code if it already works), then the `character-shot-to-video` curated
workflow, the `hyperframesManifest.ts` scaffold, an export UI action, and
tests. Plus:

- `pnpm test`, `pnpm lint`, typecheck pass.
- Single commit, conventional message.

## Constraints (hard, do not violate)

- **Do NOT duplicate or re-implement anything in `fal.ts` /
  `run-generation-job.ts` for video** if step 1's verification finds the
  path already complete.
- **Do NOT build HyperFrames rendering logic inside lumitra-studio.** The
  manifest is the entire integration surface.
- **Do NOT attempt E5b (multi-reference video binding).** Out of scope,
  separately gated on its own research pass.
- Do NOT make any live fal API call in tests.
- Stay in this worktree. Do not push to any remote.
- No em-dashes or en-dashes anywhere. Conventional commit.
- Report via `update_state`: `file_touched`, `decision`, `open_thread`
  (whether the manifest shape matched the `hyperframes` skill's
  expectations or needed a documented gap), `commit`.

## Notes

- This is the cheapest task in the whole plan to ship since video
  infrastructure already exists; this is mostly wiring plus one export
  scaffold.
  Consider dispatching it early/in parallel to build confidence before the
  heavier E3/E4 tasks land.
