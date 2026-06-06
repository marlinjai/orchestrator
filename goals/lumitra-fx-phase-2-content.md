---
task: lumitra-fx-phase-2-content
spec: docs/plans/2026-05-31-lumitra-fx-engine.md
depends_on: [lumitra-fx-phase-1-serialize]
marlin_proxy: live
marlin_proxy_categories:
  merge_after_verify: live
  branch_cleanup: live
  status_fetch: live
---

# Goal

Implement **Phase 2 (Content + interactivity)** of the spec at `docs/plans/2026-05-31-lumitra-fx-engine.md`. Add the content layers and the full interaction bus so the engine can **compose real scenes, not just the hero**: Image / Shape / Gradient content layers, blend modes across content layers, and the complete mouse (momentum / spring / axes) + scroll interactivity bus.

## Read first

- The spec, especially §3 (Interactivity store: normalized pointer, velocity, scroll progress, per-layer `momentum`/`spring`/`axes` lerp; Blend modes: material blending + custom shader blends for multiply/screen/overlay), §4.10 (Gradient / mesh gradient content), §4 "Content/source layers" (Image: texture plane cover/contain + optional displacement; Shape: SDF circle/rounded-rect/blob), §7 roadmap row "2. Content + interactivity".
- The **Phase 0/1 engine**: `src/fx/` registry, the `Layer.blend` field and `Layer.interactivity` schema already declared in the types, the existing content layers (text, noiseField, background). Phase 2 fills in `blend` for content layers and the interactivity store the types already anticipate.

## Definition of done

Per the roadmap row "2. Content + interactivity" (Outcome: "Compose real scenes, not just the hero"):

1. **Image layer**: a texture plane with `cover`/`contain` fit, opacity, optional displacement hook. Registry entry + param schema + serialize. Takes a `src` (URL).
2. **Shape layer**: SDF primitives (circle, rounded rect, blob) usable as masks/accents, with size/color/softness/blend params. Registry entry + schema + serialize.
3. **Gradient layer** (§4.10): animated smooth multi-stop gradient (3-5 color points moving on noise paths). Registry entry + schema + serialize.
4. **Blend modes for content layers**: implement `normal | screen | multiply | add | overlay` via three material `blending` where it maps, and custom shader blends for multiply/screen/overlay (the noise-fill style). The `blend` field round-trips through serialization.
5. **Full interactivity bus**: a store holding normalized pointer `(-1..1)`, pointer velocity, and scroll progress, updated on pointer/scroll events. Each frame, layers declaring `interactivity` lerp toward target with `momentum`/`spring`, constrained to `axes` (`x|y|both`), feeding `uMouse`/`uScroll` uniforms. This reproduces Unicorn's Track-mouse / Momentum / Spring / Mouse-axes knobs, exposed in leva per layer.
6. A **demo scene** (a serialized JSON scene, building on Phase 1) that composes at least Image + Shape/Gradient + an effect + interactivity, proving "real scenes" beyond the hero. The v7 hero must still render.
7. `pnpm lint` + `pnpm build` pass. §8 perf/a11y invariants preserved (mobile: clamp interaction cost; respect reduced-motion).
8. Single commit, conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree; do not push; no files outside it.
- Extend the existing registry and serialization seam. Interactivity and blend were already declared in the Phase 0 `Layer` type — implement against those fields, do not redefine the type shape unless the spec requires it (if you must, record a `decision` and keep serialization back-compatible with Phase 1 JSON).
- Engine still in `src/fx/`, editor still leva.
- No em-dashes or en-dashes. Do not change spec `status`.

## Notes

- This phase starts to touch taste (what the demo scene looks like, default param ranges that "feel good"). For purely mechanical/architectural calls, decide and record a `decision`. **Escalate** (via the proxy path) only genuine product/taste forks that would be expensive to reverse — e.g. "should Shape SDF support arbitrary polygons" or a visual-direction call on the demo scene. Default demo content can be abstract/neutral; do not invent brand copy.
- Use placeholder/local assets for the Image layer demo (e.g. something already in `public/`); do not fetch external images at build time.
- Report progress via `update_state` (`file_touched`, `commit`, `decision`, `open_thread`).
