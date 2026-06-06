---
task: lumitra-fx-phase-0-extract
spec: docs/plans/2026-05-31-lumitra-fx-engine.md
marlin_proxy: live
marlin_proxy_categories:
  merge_after_verify: live
  branch_cleanup: live
  status_fetch: live
---

# Goal

Implement **Phase 0 (Extract)** of the spec at `docs/plans/2026-05-31-lumitra-fx-engine.md`. Refactor the existing owned shader hero at `/designs/7` into a reusable engine under `src/fx/`: a `Scene` that is an ordered stack of `Layer`s driven by a typed param schema, a layer registry, and the 5 effects v7 already proves (God Rays, Bloom, Chromatic Aberration, the simplex Noise field, and the lockup text content layer) ported behind that schema. Keep the leva editor. The acceptance bar: **v7 renders through the new engine** with no visual regression.

## Read first

- The spec in full, especially: §3 Architecture (the `ParamSchema` / `Layer` / `SceneConfig` types, the layer registry, the param-system-to-editor-and-serialization seam, animation, interactivity, blend modes), §4.1/4.2/4.4/4.5 (the four effects you port), §4 "Content/source layers" (Text), §7 roadmap row "0. Extract", §8 Performance and accessibility.
- The current implementation you are extracting:
  - `src/app/designs/7/page.tsx` (mounts `IntroSequenceHero`)
  - `src/components/IntroSequenceHero.tsx` (dynamic, ssr:false wrapper)
  - `src/components/IntroSceneCanvas.tsx` (the WebGL meat: Canvas, the noise/godrays/bloom/chromatic stack, the leva controls, the useFrame loop, mouse parallax)
  - `src/components/UnicornBackground.tsx`
- The installed libraries you build on (do not add new heavy deps): `three@^0.184`, `@react-three/fiber@^9.6`, `@react-three/drei@^10.7`, `postprocessing@^6.39`, `@react-three/postprocessing@^3.0`, `leva@^0.10`. Read the relevant source under `node_modules/postprocessing/` for `GodRaysEffect`, `BloomEffect`, `ChromaticAberrationEffect` rather than guessing their option names.
- The repo's `CLAUDE.md` and existing code conventions (TypeScript strict, Next 16 app router, Tailwind classes as used in v7).

## Definition of done

Per the roadmap row "0. Extract" (Outcome: "Engine skeleton, v7 runs on it"):

1. **Core types** (`src/fx/types.ts` or equivalent) implementing the spec §3 `ParamSchema` union, `Layer`, `SceneConfig`, and `BlendMode` exactly as specified.
2. **Layer registry** with a `registerLayer(type, definition)` API. Each definition supplies: the React component (content) or Effect factory (post), the default `params` schema, and `serialize`/`deserialize`. The engine resolves `SceneConfig.layers` to components/effects by `type`. Adding a new effect = one registry entry. This is the extensibility seam every later phase extends, so get it clean.
3. **The `<LumitraScene config={SceneConfig} />` component**: renders `<Canvas>` (r3f) with content layers back-to-front, then an `<EffectComposer>` whose pass order follows layer order. A single `useFrame` walks animated params and writes uniforms (spec §3 Animation: `value(t) = base + drift * noise(t*speed + phase)` or sine). A small interactivity store feeds `uMouse` for the existing parallax (full momentum/spring/axes is Phase 2 — do not build it here, just preserve v7's current mouse parallax behavior).
4. **Five ported layers behind the param schema**, each a registry entry with its Unicorn-mapped params from the spec: `godRays` (§4.1), `bloom` (§4.2), `chromaticAberration` (§4.5), `noiseFill` (§4.4, the simplex field), and a `text` content layer (CanvasTexture lockup, emissive so it can source god rays/bloom).
5. **leva editor preserved**: one auto-generated folder per layer, fields derived from each layer's param schema (number→slider, color→picker, select→dropdown, bool→checkbox, vec2→xy). Gate it behind `?tune=1` (or an `editor` prop). The panel reads/writes the same `params` data the config holds — this single-source-of-truth is the whole point.
6. **v7 runs on the engine**: rewire `src/app/designs/7/page.tsx` (via `IntroSequenceHero`) to mount `<LumitraScene>` with a config object that reproduces the current hero. Delete the now-dead bespoke code paths in the old components that the engine replaces (no dead duplicate — per the repo's no-tech-debt rule). **Visually compare**: the hero must look and animate the same as before.
7. `pnpm lint` passes and `pnpm build` passes (Next build includes typecheck). No new TypeScript `any` leaks in the public engine surface.
8. The spec's performance/accessibility invariants from §8 are **preserved, not regressed**: `dynamic(ssr:false)`, lazy init + teardown on unmount, dpr clamp, `prefers-reduced-motion` static-frame path. If v7 already does some of these, keep them; do not remove any.
9. Spec frontmatter `status: draft` → `status: in-progress` (this is a multi-phase plan; it becomes `completed` only at Phase 4 — do NOT set it to done here).
10. Single commit on this branch, conventional-commit message describing the WHY (owned, serializable engine seam).

## Constraints

- Stay in this worktree. Do not modify files outside it. Do not push to any remote (the operator handles push/PR/merge).
- **Recommended layout** (not mandatory, but keep the seams clean): `src/fx/types.ts`, `src/fx/registry.ts`, `src/fx/LumitraScene.tsx`, `src/fx/layers/*` (content), `src/fx/effects/*` (post), `src/fx/editor/*` (leva), `src/fx/index.ts` (public exports). Later phases extend this; design for extension.
- Do NOT extract to a separate `@lumitra/fx` package yet — that is Phase 4. Engine lives in `src/fx/` for now (spec §10 decision 1).
- Stay on **leva** for the editor (spec §10 decision 2). Use **CanvasTexture** for text (spec §10 decision 3); do not pull in troika yet.
- No em-dashes or en-dashes in any output, code comments, or commit message (repo style rule).
- Do not run destructive git/shell commands. When done, output a final message that the task is complete.

## Notes

- The v1 effect priority set for the whole engine is God Rays, Bloom, Noise, Chromatic, Vignette, Grain, Distortion (spec §10 decision 4). Phase 0 ports the four that exist in v7 (God Rays, Bloom, Chromatic, Noise) plus the text layer. Vignette/Grain/RGB-Shift/Distortion are Phase 1 — do not add them here.
- Report progress via the `update_state` MCP tool: `file_touched` as you create engine files, `commit` when you commit, `decision` for any non-obvious architecture call (e.g. how you model the EffectComposer pass ordering), `open_thread` for anything you deliberately defer to a later phase.
- If a genuine architecture fork has no clear answer from the spec (e.g. registry typing strategy that materially constrains later phases), make the call that keeps phases 1-4 easiest and record it as a `decision` — do not stall.
