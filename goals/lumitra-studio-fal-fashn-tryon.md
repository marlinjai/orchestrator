---
task: lumitra-studio-fal-fashn-tryon
spec: docs/specs/2026-07-19-fal-fashn-tryon.md
shared_state: [model-taxonomy]
depends_on: []
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
  irreversible_ops: escalate
---

# Goal

DO NOT DISPATCH until the spec's frontmatter reads `status: decided` on
the default branch (satisfied once plan PR `marlinjai/lumitra-studio#83`
merges — decision #3 is resolved 2026-07-20: the task is `virtual-try-on`
with two named image inputs, garment + person). The spec's "Step 0"
prerequisite remains a hard in-task gate: a fresh live-schema research pass
against fal's FASHN endpoint, written up at
`docs/internal/research/fal-fashn-tryon.md`, since no existing research doc
in this repo covers it. Do the Step 0 research first; do not write `fal.ts`
code against a guessed schema.

Implement the leaf spec at
`docs/specs/2026-07-19-fal-fashn-tryon.md` in full: a new `virtual-try-on`
`ModelTask` (two named image inputs, garment + person, distinct from
`image-edit`), a `fal/fashn-tryon-v1-6` catalog entry, a `fal.ts` adapter,
and one new `run-generation-job.ts` branch. This is the single highest-
leverage slice in the parent plan for output quality: it preserves garment/
product pixels instead of letting a general diffusion edit redraw them.

## Read first

- The spec file in full, especially "Step 0" before anything else.
- `packages/lumitra-core/src/models/types.ts`: `MODEL_TASKS`, the single
  source of truth; widening it is a one-edit-many-callsite change, follow
  every resulting compile error to a real mapping.
- `packages/lumitra-core/src/providers/types.ts`: `ProviderJobInput.
  inputImages` (already plural, fits a two-image input without a new
  field).
- `packages/lumitra-core/src/providers/fal.ts`: `FAL_SUPPORTS`,
  `FAL_IMAGE_UTILITY_TASKS`, and `providers/submit-adapter.ts`'s
  `withGenericSubmit` dispatch flow.
- `packages/lumitra-core/src/models/catalog.ts`: several existing fal
  entries for the exact `ModelEntry` shape and cost-annotation convention.
- `src/lib/jobs/run-generation-job.ts`: `IMAGE_TASKS` set and the
  `isImageTask` branch in `persistSyncResult`.
- `docs/specs/2026-06-04-fal-image-provider.md`: the prior slice that did
  this exact shape of work for image generation.

## Definition of done

Everything the spec's "Definition of done" section lists (steps 0-7: the
research doc, `MODEL_TASKS` widening, the catalog entry, the `fal.ts`
adapter, the `run-generation-job.ts` branch, a `product-shot` curated
workflow proving the chain, tests). Plus:

- `pnpm test`, `pnpm lint`, typecheck pass.
- Single commit, conventional message.

## Constraints

- **Do NOT skip Step 0.** Writing `fal.ts` code against a guessed schema is
  exactly the mistake the fal-image-provider spec's own discipline exists
  to prevent.
- **Do NOT make any live fal API call in tests** (or, ideally, at all
  during Step 0's schema check — use fal's public docs/model page; escalate
  if a paid verification call is genuinely unavoidable, do not spend
  unilaterally).
- Do NOT remove or change the existing `image-edit` task or any other
  provider's behavior. Additive only.
- Do NOT add `FAL_KEY` to Infisical, do NOT deploy, do NOT touch production
  secrets.
- Stay in this worktree. Do not push to any remote.
- No em-dashes or en-dashes anywhere. Conventional commit.
- Report via `update_state`: `file_touched`, `decision` (the garment/person
  input-ordering convention chosen, the verified fal model id and cost),
  `open_thread`, `commit`.

## Notes

- Independent of E0-E2 at the code level and can start immediately, but
  touches `models/types.ts` (a shared-edit surface) — do not run this
  concurrently with any other task-taxonomy-widening task.
