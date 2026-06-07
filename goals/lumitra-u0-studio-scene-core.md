---
task: lumitra-u0-studio-scene-core
spec: ~/software-dev/knowledge-base/research/2026-06-06-unified-scene-schema-u0-plan.md
shared_state: [workspace, lockfile]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
verify: pnpm --filter @marlinjai/studio-scene-core run build && pnpm --filter @marlinjai/studio-scene-core run test && pnpm --filter @marlinjai/studio-scene-core run typecheck && pnpm --filter @marlinjai/studio-scene-core run lint
verify_fix_cap: 2
verify_timeout_s: 900
---

# U0: build @marlinjai/studio-scene-core (unified scene schema + migration framework)

READ THE SPEC FIRST and follow it exactly. Do NOT re-litigate the decided architecture:
`~/software-dev/knowledge-base/research/2026-06-06-unified-scene-schema-u0-plan.md`
Supporting: the reconciliation addendum `~/software-dev/knowledge-base/research/2026-06-06-scene-model-reconciliation-addendum.md` (its node/param/rule types are REGISTERED-LATER, NOT part of U0).

## What to build

A NEW render-free published workspace package `@marlinjai/studio-scene-core` in THIS repo (lumitra-studio), at `packages/studio-scene-core/`. Sibling to `packages/lumitra-core` (which is the `@marlinjai/studio-core` spine: do NOT touch it). Mirror the existing studio packages' tsup + vitest + tsconfig toolchain. `package.json` name `@marlinjai/studio-scene-core`, with `publishConfig.access: public` (per `knowledge-base/standards/package-naming.md`) and npm scripts named exactly `build`, `test`, `typecheck`, `lint` (the verify gate runs these).

ZERO render dependencies (no three, no @react-three/*, no react). Pure TypeScript types + functions + Zod. NO import edge to `@marlinjai/studio-core` (providers/brand/jobs): the package is the schema only.

Exports (all shapes copied verbatim from the spec, which cites the source lines):
- `SceneNode` discriminated union + `NodeId`/`NodeType`/`NodeKind`/`Transform`/`BlendMode`/`InteractivitySpec`.
- `ParamValue` (values-only) and `ParamSpec` (registry presentation+validation), same `type` discriminant.
- `Scene`/`CanvasSettings`/`SchemaVersion` + glossary `Shot`/`Track`/`Storyboard` types.
- `AnimateBinding` (oscillator | keyframes) + a clock-injected `value(t)` evaluator that ACCEPTS injected `t = frame/fps`.
- `NodeDefinitionRegistry` + `registerNode`/`getNodeDefinition`/`listNodeDefinitions`, enforcing per-kind structural legality on load (strip a transform on fx.* nodes, a blend on non-drawing nodes, reject children violating allowedChildren).
- values-only `serializeScene`/`deserializeScene` (registry-default driven; drop-unknown + coerce-to-default resilience promoted to structural fields).
- `migrations/` keyed `(fromSchema -> toSchema)`, runnable lazily on read AND as a one-time batch, with the v1 -> v2 migration (the 5 steps in the spec: detect legacy `layers` array, wrap into an `fx.stack` root, `toNode` each layer with the `fx.` prefix, lift size/background/fps/dpr into `canvas`, stamp `version = {schema:2, content:{fx:1}}`).
- a Zod `{ nodeId, path, value }` patch validator plus `add-node`/`remove-node`/`reorder`/`rewire-edge`, validated against the registry.
- the `Asset` TS mirror copied VERBATIM from `prisma/schema.prisma` (the `AssetSubtype` enum, 14 members, + the `Asset` model fields; mirror scalars only, omit Prisma relations). NO `brandId`/`version`/`tags`; `costUsd` is a string in TS (Decimal at the DB).
- Register `fx.stack` + all `fx.*` content/post node types (mirror the builtin list at `~/software-dev/ERP-suite/projects/lumitra-web/packages/fx/src/builtins.ts`, prefixed `fx.`, with the legality flags from the spec Section 4).

## Fixtures + golden round-trip

Copy the REAL v1 hero-scene blobs into `src/__fixtures__/`:
`~/software-dev/ERP-suite/projects/lumitra-web/src/scenes/v7.json` and `~/software-dev/ERP-suite/projects/lumitra-web/src/scenes/demo-phase-2.json`.
Golden test: each fixture deserializes, migrates v1 -> v2 to `{ root: <fx.stack> }`, and re-serializes BYTE-IDENTICAL at the values level. This is the regression oracle.

## Acceptance (definition of done)

1. The package builds (tsup), typechecks (`tsc --noEmit`), and lints clean.
2. Golden round-trip is byte-identical on BOTH v1 hero fixtures.
3. v1 -> v2 migration is lossless, run both lazily (inside deserializeScene) and as a batch; stamps `{schema:2, content:{fx:1}}`.
4. Registry load-validation enforces per-kind structural legality; every registered node type resolves (registry-completeness).
5. The Zod patch validator accepts in-range / correctly-typed patches and rejects out-of-range / wrong-type ones before apply.
6. A values-only v2 round-trip critic test (serialize, deserialize, re-serialize, assert byte-identical) is part of the package test suite.
7. The verify command (the package build + test + typecheck + lint) is green.

NO 3D node types. NO version bump beyond defining `schema: 2` as the migration target. The state-machine / character / rule types from the addendum are noted as registry-extensible but NOT implemented in U0.

## Hard constraints

- Follow the spec; the decided architecture is frozen (one SceneNode union, two render adapters, values-only, one mutation grammar). ADD, do not re-derive.
- Conventional commits, body lines <= 100 chars, NO em-dashes or en-dashes (use colon/parens/comma/period).
- Touch ONLY the new `packages/studio-scene-core/`. Do NOT modify `packages/lumitra-core`, the providers/jobs, the prisma schema, any auth code, the Dockerfile, or any app route.
- Do NOT deploy, publish, run `infisical`/secrets, or touch infra. The package tests are PURE (JSON fixtures, no DB, no network).
- Do NOT rename the `packages/lumitra-core` directory (it intentionally holds `@marlinjai/studio-core`).
- Single branch, commits on that branch; never push to main, never `gh pr merge` (the operator merges).
