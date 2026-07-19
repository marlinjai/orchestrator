---
task: lumitra-studio-character-injection
spec: docs/specs/2026-07-19-character-injection.md
shared_state: []
depends_on: [lumitra-studio-character-db-migration]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

DO NOT DISPATCH until the spec's frontmatter reads `status: decided` — the
spec explicitly requires Marlin's confirmation of the brand-vs-character
reference precedence rule (decision #2 in the parent plan) before
implementation, and `lumitra-studio-character-db-migration` (E0) has
merged. Implement the leaf spec at
`docs/specs/2026-07-19-character-injection.md` in full:
`injectCharacterReferences.ts` (structural clone of
`injectBrandReferences.ts`) plus a `characterSlug` option on
`/api/generate`, folding an approved character's locked descriptor prompt
and reference images into every generation the way brand references already
are.

## Read first

- The spec file in full.
- `src/lib/brand/injectBrandReferences.ts`: read in full, this is a
  near-literal structural clone.
- `src/app/api/generate/route.ts`: the exact injection point in
  `handleGenerate` (~lines 109-156).
- `packages/lumitra-core/src/models/catalog.ts` and
  `ModelCapabilities.maxInputImages`: the existing clamp mechanism, reuse
  it.
- `packages/lumitra-core/src/jobs/types.ts`:
  `GenerateImageJobInputSchema`.

## Definition of done

Everything the spec's "Definition of done" section lists: the injection
helper, the confirmed precedence-allocation function, the route changes,
the schema widening, the `Asset.characterId` write-through in
`run-generation-job.ts`'s image persistence branch, and tests. Plus:

- `pnpm test`, `pnpm lint`, typecheck pass.
- Single commit, conventional message.

## Constraints

- **Do NOT change brand-only behavior.** A request with `brandSlug` and no
  `characterSlug` must produce byte-identical output to today (regression
  test against existing brand injection tests as the oracle).
- **Do NOT invent the precedence rule if it was not confirmed before
  dispatch.** If you find the spec still `proposed` when you start, stop
  and escalate rather than guessing.
- Do NOT touch the 3D generation branch in `/api/generate/route.ts`.
- Stay in this worktree. Do not push to any remote.
- No em-dashes or en-dashes anywhere. Conventional commit.
- Report via `update_state`: `file_touched`, `decision` (the exact
  precedence and prompt-ordering choices made), `open_thread`, `commit`.

## Notes

- No prisma/migration touches once E0 exists, so this can dispatch in
  parallel with `lumitra-studio-character-sheet-workflow` (E1).
- `lumitra-studio-fal-fashn-tryon` (E3) and `lumitra-studio-shot-review-
  qc-loop` (E4) both build on the `Asset.characterId` lineage this task
  writes; get it right before those dispatch.
