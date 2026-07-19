---
task: lumitra-studio-character-sheet-workflow
spec: docs/specs/2026-07-19-character-sheet-workflow.md
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

DO NOT DISPATCH until the spec's frontmatter reads `status: decided` AND
`lumitra-studio-character-db-migration` (E0) has merged. Implement the leaf
spec at `docs/specs/2026-07-19-character-sheet-workflow.md` in full: a
curated generation-workflow DAG definition (`character-sheet`) that turns
one seed-face generation into a multi-view turnaround sheet, plus the
human-approve gallery that promotes selected outputs into frozen
`CharacterReference` rows. This is the roster-minting pipeline — the human
approval step is a hard QC gate, not a suggestion.

## Read first

- The spec file in full.
- `src/lib/workflow/curated.ts`: the `hero-product-shot` and `image-pair`
  definitions, the exact template for a multi-node curated DAG.
- `packages/lumitra-core/src/workflow/types.ts` and `resolve.ts`: the
  binding grammar (literal/param/ref) this new definition must express
  itself through, with zero engine changes.
- `packages/lumitra-core/src/providers/fal.ts`: the Nano Banana 2 edit
  endpoint's multi-reference input shape.
- `src/components/workflows/EditableWorkflowCanvas.tsx` and
  `NodeResultLightbox.tsx`: reuse these for the approve step, do not build a
  new canvas component.
- `src/lib/character/repository.ts` and the `/references/upload` route from
  E0.

## Definition of done

Everything the spec's "Definition of done" section lists (sheetPrompts.ts,
the curated `character-sheet` definition, the approve-and-freeze UI seam,
tests). Plus:

- `pnpm test`, `pnpm lint`, typecheck pass.
- Single commit, conventional message.

## Constraints

- **Do NOT modify the workflow DAG engine**
  (`packages/lumitra-core/src/workflow/{types,resolve,plan,registry}.ts`).
  Pure consumer only. If the binding grammar cannot express what the spec
  needs, that is a scope_change: escalate, do not patch the engine
  unilaterally.
- **Do NOT auto-promote workflow outputs into `CharacterReference` rows.**
  The human-approve click is mandatory.
- Do NOT make any live fal API call in tests.
- Stay in this worktree. Do not push to any remote.
- No em-dashes or en-dashes anywhere. Conventional commit.
- Report via `update_state`: `file_touched`, `decision` (how run-time
  templating of view prompts was resolved against the binding grammar),
  `open_thread`, `commit`.

## Notes

- No prisma/migration touches once E0 exists, so this can dispatch in
  parallel with `lumitra-studio-character-injection` (E2).
