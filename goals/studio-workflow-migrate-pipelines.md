---
task: studio-workflow-migrate-pipelines
spec: src/lib/workflow
verify: pnpm test
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Prove the generation-workflow engine on the REAL pipelines (backlog E3, the safe half): express the existing image-generation and the 3D chain as declarative `WorkflowDefinition`s, register them, and add a parity/integration test that runs them through the real executor and asserts equivalent behaviour to the current bespoke handlers. Do NOT yet cut `/api/generate` over to the engine: keep the existing handlers live (no big-bang). The cutover is a deliberate later slice.

## Read first

- The run infra just landed on main (#33): `src/lib/workflow/executor.ts` (`startWorkflowRun` / `advanceWorkflow`), `repository.ts`, `method-map.ts` (maps `method` -> `ProviderClient.<method>`), `executor.spec.ts` (the real-DB integration-test pattern to MIRROR), `constants.ts` (`DEFAULT_WORKSPACE_ID`).
- The workflow schema in `@marlinjai/lumitra-core/workflow` (`packages/lumitra-core/src/workflow/`): `WorkflowDefinition`, `WorkflowNode`, `Binding` (literal/param/ref), `registerWorkflow`/`getWorkflow`/`listWorkflows`. The `ref` binding is the edge grammar.
- The current bespoke handlers (what you are expressing as definitions): `src/lib/jobs/handlers/generate-image.ts`, `generate-3d.ts`, `remesh-3d.ts`, `texture-3d.ts`, `complete-3d.ts`, plus the chaining in `src/lib/jobs/worker.ts` + `src/lib/jobs/pollers/3d.ts`. Read these to get the exact provider methods, inputs, and how outputs feed the next step.
- The `ProviderClient` methods the nodes call: `generateImage`, `generate3D`, `remesh3D`, `texture3D`.

## Definition of done

1. **Two registered `WorkflowDefinition`s** added to the EXISTING `src/lib/workflow/curated.ts` (a prior slice created it; it already registers an example `hero-product-shot` via `registerWorkflow` inside `ensureCuratedWorkflows()`). EXTEND that module + that function, do NOT create a parallel definitions file. Mirror its existing shape:
   - `image-gen`: a single node, `method: generateImage`, model + prompt/params as `param` bindings, matching what `generate-image.ts` does today.
   - `3d-pipeline`: three nodes `generate3D -> remesh3D -> texture3D`, wired with `ref` bindings (each step's input references the prior node's output, e.g. the GLB url / parent asset id), matching the current `generate-3d -> remesh-3d -> texture-3d` chain.
   - Both must pass the registry's definition-time validation (`parseWorkflowDefinition`).
2. **A parity integration test** (mirror `executor.spec.ts`: real test Postgres, real pg-boss queue, but the `ProviderClient` MOCKED, no real fal calls / no money): run each definition through `startWorkflowRun` + `advanceWorkflow`, and assert the engine produces the equivalent run outcome the bespoke handlers would: the right node sequence executes, ref bindings resolve (the 3D chain passes the GLB through), asset lineage (`derivedFromIds`) is written across the chain, and cost rolls up. `pnpm test` GREEN.
3. The existing `/api/generate` + the 4 handlers remain UNCHANGED and working (coexistence; no cutover this slice).
4. Single conventional-commit on this branch.

## Constraints

- Do NOT cut `/api/generate` over to the engine, do NOT delete or rewire the bespoke handlers / `worker.ts` / `pollers/3d.ts`. This slice only ADDS the definitions + the parity test. (The cutover is a separate, riskier slice.)
- Do NOT call the real fal provider in tests (real money + flaky). MOCK the `ProviderClient`; assert the chaining/lineage/binding logic, not real generations.
- Do NOT change the workflow schema/registry (E1) or the executor/repository (#33). You consume them.
- No dependency bumps. Stay in this worktree, do not push to a remote. Output a final completion message when done.

## Notes

- The point is parity confidence: "the same image-gen and 3D chain, now expressed declaratively, runs identically through the generic engine." That is what makes it safe to cut `/api/generate` over later.
- If a current handler does something the declarative schema cannot yet express (e.g. an async-poll step that does not fit a simple node), file an `open_thread` describing the gap precisely rather than forcing it; that is real signal for the schema, not a thing to hack around.
