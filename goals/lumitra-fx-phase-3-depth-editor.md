---
task: lumitra-fx-phase-3-depth-editor
spec: docs/plans/2026-05-31-lumitra-fx-engine.md
depends_on: [lumitra-fx-phase-2-content]
marlin_proxy: live
marlin_proxy_categories:
  merge_after_verify: live
  branch_cleanup: live
  status_fetch: live
---

# Goal

Implement **Phase 3 (Depth + editor UX)** of the spec at `docs/plans/2026-05-31-lumitra-fx-engine.md`. Make the engine **feel like a crafting tool**: add depth/finishing effects (Bokeh/DoF, Pixelate, Halftone) and the editor UX that turns a param panel into a layer editor (add / remove / reorder / toggle layers, presets). Optionally add a perf-gated Fluid effect.

## Read first

- The spec, especially §4.3 (Bokeh/DoF: CoC from focus distance, disc sample; for the 2D scene use a "mix radius" mask matching Unicorn's Bokeh radius + mix radius; use-case = intro focus-pull animating radius high→0), §4.8 (Pixelate via `PixelationEffect`, Halftone/DotScreen via `DotScreenEffect`), §4.7 (Liquid/Fluid, advanced, **optional**, behind a perf/device gate — Pavel Dobryakov MIT sim), §5 The editor (layer visibility toggles, add/remove layer, reorder up/down; presets gallery), §7 roadmap row "3. Depth + editor UX".
- The **Phase 0-2 engine**: the registry (`registerLayer`), the leva editor integration, the `SceneConfig.layers` ordering, serialization. Phase 3 adds editor operations that mutate `layers` (add/remove/reorder/toggle) and persist via the Phase 1 autosave/export path.

## Definition of done

Per the roadmap row "3. Depth + editor UX" (Outcome: "Crafting tool feels like Unicorn"):

1. **Bokeh / DoF** effect (§4.3): registry entry + param schema (radius, mix radius, easing, focus position, invert) + serialize. Demonstrate the intro focus-pull (animate radius high→0).
2. **Pixelate** and **Halftone/DotScreen** effects (§4.8): registry entries + schemas + serialize, mapped to `postprocessing`'s `PixelationEffect` / `DotScreenEffect`.
3. **Editor layer operations**: in the leva-based editor, support add layer (pick a registered type), remove layer, reorder (up/down), and toggle visibility — all mutating `SceneConfig.layers` and round-tripping through Phase 1 serialization/autosave. A layer-list UI (even minimal) that lists layers in back-to-front order with these controls.
4. **Presets**: a small set of named preset scenes (serialized configs) selectable in the editor that load into the canvas. At least 3 presets that show off the engine (e.g. a god-rays hero, a noise-field gradient, a bokeh focus-pull).
5. **Fluid (optional, gated)**: if implemented, it must be behind a device/perf gate (capability check + a leva toggle, off by default on mobile/low-fps), using the cited MIT fluid approach. If perf risk is too high to land cleanly, **skip it and file an `open_thread`** rather than shipping something that tanks the frame budget — note this as a `decision`.
5b. **True `overlay` blend mode** (carried from Phase 2): Phase 2 approximated content-layer `overlay` with a screen-style `CustomBlending` because a real overlay needs to sample the destination color (a per-layer framebuffer copy pass), which Phase 2 had no render-target infrastructure for. Phase 3 introduces render targets for Bokeh/DoF anyway — reuse that to implement a correct `overlay` (and any other destination-reading blend) for content layers via a copy/read pass. See `src/fx/layers/contentBlend.ts` (the documented approximation) and the Phase 2 decision log. If after building the DoF render-target path a true overlay is still disproportionately expensive for the visual gain, keep the approximation but record an explicit `decision` saying so.
6. `pnpm lint` + `pnpm build` pass. §8 perf/a11y invariants strictly preserved: dpr clamp, PerformanceMonitor downshift (drop dpr to 1 + disable heavy passes on low fps), reduced-motion static frame, mobile skips Fluid/heavy passes. Phase 3 is where the effect stack gets heaviest — keep the desktop-60/mobile-30 floor.
7. Single commit, conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree; do not push; no files outside it.
- Extend the existing registry/editor/serialization seams; do not fork a parallel editor.
- Engine still in `src/fx/`, still leva (a custom panel is explicitly optional and NOT required this phase — spec §10 decision 2 says leva is plenty; only invest in a custom panel if it is the cheapest path to the layer-list UX, and record that as a `decision`).
- No em-dashes or en-dashes. Do not change spec `status`.

## Notes

- This is the most taste-heavy phase. Mechanical/architectural calls: decide and record. **Escalate** genuine product/taste forks — e.g. whether to invest in a full custom editor panel vs. staying in leva, the visual direction of the shipped presets, or whether Fluid is worth the perf budget for this product. Do not guess on expensive-to-reverse visual-direction calls.
- Performance is non-negotiable here (most passes stacked). If a feature can't hit the frame budget, gate it or defer it via `open_thread`; do not regress the floor to ship a feature.
- Report progress via `update_state` (`file_touched`, `commit`, `decision`, `open_thread`).
