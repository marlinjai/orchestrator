---
task: state-dts-typed-contract
verify: uv run pytest -q && uv run ruff check orchestrator/ tests/
# Target repo (--project): ~/software-dev/orchestrator  (the orchestrator's OWN repo: high-stakes)
# Wave 1 / leaf L3 -- THE KEYSTONE for the Wave-3 board. Decision source:
#   knowledge-base/plans/2026-06-17-autonomous-dev-platform-roadmap.md (Wave 1: "State contract (state.d.ts)")
#   docs/handovers/2026-06-20-roadmap-driver-handover.md (L3)
shared_state: [state-schema]
---

# Goal

Codegen a TypeScript type contract, `types/state.d.ts`, from the Pydantic v2 `State` model so the
future Wave-3 Kanban board can never silently drift from `state.json`. The generator must be a
SELF-CONTAINED pure-Python emitter (the repo has no node toolchain and must not gain one): walk
`State.model_json_schema()` and emit a complete `.d.ts`, with a test that regenerates and diffs so
`uv run pytest` fails the moment the model changes without the contract being regenerated. This is
cheap, zero-runtime-blast-radius, and the board's data layer.

## Read first

- `orchestrator/state.py`: the `State` model and EVERY nested model (`PlanStep`, `Decision`, `Handover`,
  `CommitEntry`, `FileTouched`, `VerifyRecord`, `HeldOutRecord`, `IterationUsage`, `AutonomyStats`) plus
  the `Literal` aliases (`PlanStatus`, `TaskStatus`, `DecidedBy`, `VerifyStatus`). This is the full surface the `.d.ts` must cover.
- `tests/test_state.py` (round-trip serialization tests; the new freshness test fits this style) and `tests/fixtures/state_sample.json`.
- `pyproject.toml` (Pydantic >=2.6 in use; `model_json_schema()` is the source) and `.github/workflows/verify.yml` (the CI gate runs `uv run pytest -q` + `uv run ruff check`).

## Scope

1. **`scripts/gen_state_dts.py`** (new): a pure-Python generator with NO new third-party dependency
   (no `pydantic2ts`, no node `json-schema-to-typescript`). Read `State.model_json_schema()` and emit
   `types/state.d.ts`: one `export interface` per object model, `export type` unions for the `Literal`
   aliases, correct optional (`?`) for non-required / `| null` fields, `string` for ISO datetime fields,
   arrays as `T[]`. Deterministic output (stable key ordering) so the diff test is stable. Runnable as `uv run python scripts/gen_state_dts.py [--check]`.
2. **`types/state.d.ts`** (generated, committed): the materialized contract. Header comment marks it
   generated-do-not-edit and names the generator + the `State` source.
3. **Freshness test** in `tests/test_state_dts.py` (new): regenerate into a temp buffer and assert it
   byte-matches the committed `types/state.d.ts`. Failure message tells the dev to run the generator.
   This is the anti-drift guard that makes the contract trustworthy.
4. **`--check` mode** on the generator (regenerate + diff, non-zero on mismatch) so the same guard is
   available to CI / pre-commit later without standing one up now.

## Definition of done

- `uv run python scripts/gen_state_dts.py` writes a complete `types/state.d.ts` covering all 30 `State`
  fields + all 9 nested models + all 4 `Literal` unions; re-running is a no-op (idempotent).
- `tests/test_state_dts.py` passes and FAILS if `state.py` changes without regenerating (prove by a local experiment, then revert).
- `uv run pytest -q` passes; `uv run ruff check orchestrator/ tests/` clean (the generator under `scripts/` follows the repo's lint config; widen the ruff target only if `scripts/` is not already covered, and keep `verify` accurate to what you change).
- ROADMAP.md "Shipped" updated with the slice in the EXISTING entry format (no new columns).
- Single conventional commit describing the WHY (typed contract so the board can't drift from state.json).

## Constraints

- Stay in this worktree; do not push. This touches the orchestrator's OWN source (high-stakes): make
  no change outside the generator, the generated file, the test, and the ROADMAP line.
- NO new runtime/dev dependency and NO node toolchain. Pure-Python emitter only.
- Do not hand-write `state.d.ts`; it must be generated, or the anti-drift guarantee is a lie.
- No em-dashes / en-dashes (including inside the generated `.d.ts` header). Conventional-commit message.

## Notes

- The whole point is the FRESHNESS TEST, not the file. A committed `.d.ts` with no regeneration guard is exactly the drift the roadmap is trying to prevent.
- Keep the generator dumb and total: a small recursive walk over the JSON-schema `$defs` + top-level properties. Do not try to be a general schema-to-TS tool (that is the roadmap's named scope-creep risk); cover what `State` actually uses.
