---
task: lumitra-studio-shot-review-qc-loop
spec: docs/specs/2026-07-19-shot-review-qc-loop.md
shared_state: []
depends_on: [lumitra-studio-character-injection, lumitra-studio-fal-fashn-tryon]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

DO NOT DISPATCH until the spec's frontmatter reads `status: decided` AND
both `lumitra-studio-character-injection` (E2) and `lumitra-studio-fal-
fashn-tryon` (E3) have merged — there is nothing meaningful to rank against
before either identity or garment-fidelity generation paths exist. Implement
the leaf spec at `docs/specs/2026-07-19-shot-review-qc-loop.md` in full: an
app-level review surface that generates N candidates per shot (using the
already-shipped `candidateCount` parameter), scores each with an
already-shipped `image-to-json` vision ranking call against the character
sheet and/or source garment image, and surfaces sorted results for a human
approve click.

## Read first

- The spec file in full.
- `packages/lumitra-core/src/providers/types.ts`:
  `GenerateImageInput.candidateCount` and `ProviderResult`.
- `packages/lumitra-core/src/providers/fal.ts`: `FAL_VISION_TASKS` and the
  `image-to-json` sync path.
- `src/lib/jobs/run-generation-job.ts`: the `task === 'image-to-json'`
  branch in `persistSyncResult`.
- `packages/lumitra-core/src/workflow/{plan,resolve}.ts`: read in full to
  confirm there is genuinely no for-each/select node kind before building
  around that constraint — verify, do not assume from the spec summary
  alone.
- `src/components/workflows/NodeResultLightbox.tsx` and
  `EditableNodeCard.tsx`: reusable gallery/lightbox components.

## Definition of done

Everything the spec's "Definition of done" section lists (the ranking
schema/prompt, the ranking job helper, the app-level review loop, the review
UI, tests). Plus:

- `pnpm test`, `pnpm lint`, typecheck pass.
- Single commit, conventional message.

## Constraints

- **Do NOT extend the workflow DAG engine with a for-each or
  select-best-of-N node kind.** This is a deliberate scope boundary set in
  the parent plan's decision #4, not an oversight. If the DAG genuinely
  needs this, that is separate backlog work: file it as an `open_thread`,
  do not build it here.
- **Do NOT let ranking scores auto-reject/auto-delete a candidate.** Verdict
  `"reject"` is a UI signal only, never an automated deletion.
- Stay in this worktree. Do not push to any remote.
- No em-dashes or en-dashes anywhere. Conventional commit.
- Report via `update_state`: `file_touched`, `decision` (where the review UI
  landed in the app's navigation, the sort/tie-break rule used),
  `open_thread` (the DAG select-node backlog item), `commit`.

## Notes

- This loop multiplies spend 3-4x per shot (N candidates + N ranking
  calls). Surface a running `costUsd` total in the review UI from day one
  using the existing `Job`/`Asset` fields, no new tracking mechanism.
