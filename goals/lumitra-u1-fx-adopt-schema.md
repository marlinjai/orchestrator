---
task: lumitra-u1-fx-adopt-schema
spec: ~/software-dev/knowledge-base/research/2026-06-07-u1-fx-adopt-scene-core-plan.md
shared_state: [lockfile]
marlin_proxy: shadow
marlin_proxy_categories:
  scope_change: escalate
  product_decision: escalate
  risk_tradeoff: escalate
verify: pnpm install && pnpm --filter @lumitra-web/fx run test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
verify_timeout_s: 1200
---

# U1: wire @lumitra-web/fx onto published @marlinjai/studio-scene-core (zero hero regression)

READ THE SPEC FIRST and follow it exactly. Do NOT re-litigate the decided architecture:
`~/software-dev/knowledge-base/research/2026-06-07-u1-fx-adopt-scene-core-plan.md`
Supporting context (decided, frozen): the strategy keystone `2026-05-31-lumitra-unified-platform-strategy.md` (Phase U1) and the U0 plan `2026-06-06-unified-scene-schema-u0-plan.md`.

This is a BRIDGE, not a rewrite. The FX render path (`packages/fx/src/LumitraScene.tsx`, `packages/fx/src/serialize.ts`) does NOT change. FX gains a boundary adapter that accepts the unified `{ root: fx.stack }` scene and converts it DOWN into FX's existing internal `SceneConfig`, so the rendered pixels are identical. `@marlinjai/studio-scene-core@0.1.0` is live on npm; consume it.

## What to build (in this repo, lumitra-web)

1. `packages/fx/package.json`: add `"@marlinjai/studio-scene-core": "^0.1.0"` to `dependencies` (caret semver, NOT `workspace:*`: studio and web are separate repos, no shared workspace). Add `vitest` as a devDependency and a `"test": "vitest run"` script (the verify gate runs it).

2. `packages/fx/src/registry.ts`: rename the existing `registerLayer` to `registerNode` (same signature, same local Map of `LayerDefinition`), then add `export const registerLayer = registerNode;` as a thin alias. Leave `getLayerDefinition` / `listLayerDefinitions` unchanged. Do NOT merge FX's local registry into scene-core's `NodeDefinitionRegistry`: the two coexist by design (scene-core = render-free schema/legality authority with `fx.`-prefixed keys; FX-local = render authority carrying the React `Component`, un-prefixed keys).

3. `packages/fx/src/builtins.ts`: switch the 15 `registerLayer(...)` calls + the import to `registerNode(...)`.

4. NEW `packages/fx/src/unified.ts`: `export function sceneConfigFromUnified(data: unknown): SceneConfig`.
   - Call scene-core's `deserializeScene` (runs migrations: accepts a v1 flat blob, a v2 `{root}` blob, or a live `Scene`) to normalize to a `Scene` with `root: fx.stack`.
   - Walk `scene.root.children` back-to-front (the `fx.stack` child order). For each `SceneNode`: strip the `fx.` prefix to get FX's local type, look it up via `getLayerDefinition(localType)`, hydrate the values-only `node.params` into FX's full `ParamSchema` by applying each value over `def.defaultParams` (REUSE FX's existing param coercion from `serialize.ts` -- extract a shared helper, do not duplicate). Copy `visible`, `blend` (default `"normal"`), `interactivity` verbatim. Unwrap scene-core's `animate {mode:"oscillator",speed,drift,phase}` back to FX's flat `{speed,drift,phase}`; drop `keyframes` bindings (no FX runtime yet) with a console warning, not a crash. Drop unknown types with a warning (mirror FX resilience).
   - Lift `scene.canvas.{size,background,fps,dpr}` to top-level `SceneConfig` fields, passing through FX's existing narrowing (`fps: 30|60|120`, `dpr: [number,number]`).
   - Return a `SceneConfig` with `version: SCENE_SCHEMA_VERSION` (FX's `1`).

5. `packages/fx/src/index.ts`: `export { sceneConfigFromUnified } from "./unified";`, re-export `registerNode` alongside `registerLayer`, update the JSDoc bullet to note `registerNode` primary / `registerLayer` alias.

6. `src/scenes/v7.ts` (app, NOT package): route the hero load through the adapter:
   ```ts
   import { sceneConfigFromUnified, type SceneConfig } from "@lumitra-web/fx";
   import v7Json from "./v7.json";
   export const v7SceneConfig: SceneConfig = sceneConfigFromUnified(v7Json);
   ```
   Do NOT change `v7.json` (the migration handles v1 to v2 transparently). Also route `src/scenes/demoPhase2.ts` the same way for consistency. Leave preset-based `demoPhase3.ts` alone.

## Zero-regression oracle (the regression gate)

Add `packages/fx/src/__tests__/unified.equivalence.test.ts`. The FX render is a pure function of `SceneConfig`, so structural equality of the config is a sound proxy for pixel-identity of the hero:
```
deepEqual( deserializeScene(v7Json), sceneConfigFromUnified(v7Json) )
```
Assert the two `SceneConfig`s are deep-equal: same layers, same param values, same order, same canvas, same ids. Cover BOTH `src/scenes/v7.json` and `src/scenes/demo-phase-2.json`. Keep the test dependency-light (pure adapter + loaders, NO R3F/WebGL). This is the machine-checkable proof the operator's later visual review backstops.

CRITICAL: v7's `godRays` post-effect binds to `text-lockup` by id (`sourceLayerId`). The adapter must NOT rewrite ids, or the post-effect binding silently breaks. The deepEqual test catches this.

## Acceptance (definition of done)

1. `pnpm --filter @lumitra-web/fx run test` is green: the equivalence oracle passes on both hero fixtures.
2. `pnpm typecheck` clean (app + fx, against the published scene-core types).
3. `pnpm lint` clean.
4. `pnpm build` green (`pnpm --filter @lumitra-web/fx build && next build`): the adapter compiles and the whole app builds.
5. fx consumes `@marlinjai/studio-scene-core@^0.1.0` as a published dependency (NOT `workspace:*`); the lockfile is regenerated and committed.
6. `registerNode` is the primitive, `registerLayer` is a working alias, builtins register via `registerNode`.
7. `src/scenes/v7.ts` loads via `sceneConfigFromUnified`; the render path (`LumitraScene.tsx`, `serialize.ts`) is UNTOUCHED.

## Hard constraints

- Follow the spec; the architecture is frozen (one SceneNode union, two render adapters, values-only, the adapter at the boundary). ADD, do not re-derive.
- Touch ONLY: `packages/fx/{package.json, src/registry.ts, src/builtins.ts, src/unified.ts (new), src/index.ts, src/__tests__/unified.equivalence.test.ts (new)}`, `src/scenes/{v7.ts, demoPhase2.ts}`, and the regenerated `pnpm-lock.yaml`. Do NOT touch `LumitraScene.tsx`, `serialize.ts` (except extracting a shared param-coercion helper that the adapter reuses), any other app route, or any infra/CI.
- Do NOT attempt to unify the two registries (that would touch the render path; out of scope for U1).
- Do NOT deploy, publish, run `infisical`/secrets, or touch infra. The verify gate is fully headless (CI proves `next build` needs no build-time secrets). There is no `.infisical.json` in this repo and none is needed.
- Conventional commits, body lines <= 100 chars, NO em-dashes or en-dashes (use colon / parens / comma / period). No `--no-verify`.
- Single branch, commits on that branch; never push to main, never `gh pr merge` (the operator merges after the human FX visual-regression review).
