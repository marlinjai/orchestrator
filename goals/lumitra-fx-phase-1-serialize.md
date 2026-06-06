---
task: lumitra-fx-phase-1-serialize
spec: docs/plans/2026-05-31-lumitra-fx-engine.md
depends_on: [lumitra-fx-phase-0-extract]
marlin_proxy: live
marlin_proxy_categories:
  merge_after_verify: live
  branch_cleanup: live
  status_fetch: live
---

# Goal

Implement **Phase 1 (Serialize)** of the spec at `docs/plans/2026-05-31-lumitra-fx-engine.md`. Make scenes **reusable files instead of hardcoded JSX**: full `SceneConfig` JSON in/out, localStorage autosave while tuning, export/import, and an embed-snippet button. Add four more effects (Vignette, Grain, RGB Shift, Distortion) behind the param schema. This is the MVP that proves the thesis: **the leva panel writes a reusable scene file** (the thing Unicorn gives you that v7 lacked).

## Read first

- The spec, especially §3 (param-system-to-serialization seam), §5 The editor (Persistence: Export/Import/autosave/embed snippet), §4.8 (Grain/Vignette/RGB Shift — most already in `postprocessing`), §4.6 (Distortion/Displacement/Ripple), §6 Package and API (the `<LumitraScene config>` / `createScene` shapes you are serializing toward), §7 roadmap row "1. Serialize".
- The **Phase 0 engine you are extending**: `src/fx/` — the registry, the `Layer`/`SceneConfig`/`ParamSchema` types, each layer's `serialize`/`deserialize`. Phase 1 is mostly "make the registry's serialize/deserialize round-trip a whole scene and persist it."
- `node_modules/postprocessing/` sources for `VignetteEffect`, `NoiseEffect` (grain), `ChromaticAberrationEffect` / an RGB-shift pass, and a displacement approach for Distortion (§4.6 GLSL: `uv += (texture(noise, uv*scale+t).rg - 0.5) * strength`).

## Definition of done

Per the roadmap row "1. Serialize" (Outcome: "Scenes are saved/reused, not hardcoded. The Unicorn-parity unlock"):

1. **Serialize**: a function that walks a live `SceneConfig` (params, layer order, visibility, blend, animate, interactivity) and produces canonical JSON. **Deserialize**: load that JSON back into a running scene via `<LumitraScene config={json} />`. Round-trip must be lossless: export → import reproduces the identical scene.
2. **Export UI**: a button in the editor that serializes the current scene to JSON and offers both **download** (`.json` file) and **copy to clipboard**.
3. **Import UI**: load a JSON scene (file picker or paste) and render it.
4. **Autosave**: while the editor is open, debounce-persist the working `SceneConfig` to `localStorage` (namespaced per scene id) and restore it on reload. Provide a "reset to default" affordance.
5. **Embed snippet**: a button that outputs a ready-to-paste `<LumitraScene config={...} />` snippet (and/or a by-id form) for the current scene.
6. **Four added effects**, each a registry entry with its param schema and leva folder, all serializable like the Phase 0 effects: `vignette` (§4.8), `grain` (§4.8, `NoiseEffect`/dither), `rgbShift` (§4.8), `distortion` (§4.6, type: noise/texture/ripple, strength/scale/speed/mouse-influence).
7. The v7 hero is **re-saved as a serialized scene file** (e.g. a JSON the page loads) rather than an inline hardcoded config, demonstrating the unlock end to end. The hero must still render identically.
8. `pnpm lint` + `pnpm build` pass. §8 perf/a11y invariants preserved.
9. Single commit, conventional-commit message describing the WHY (scenes become reusable files).

## Constraints

- Stay in this worktree; do not push; no files outside it.
- Extend the Phase 0 registry/serialize seam — **do not fork a parallel serialization path**. If Phase 0's `serialize`/`deserialize` per-layer hooks are incomplete, complete them in place.
- Keep the editor on leva. Engine still lives in `src/fx/` (no package extraction yet).
- No em-dashes or en-dashes anywhere, commit message included.
- Do not change the spec's `status` (it stays `in-progress` until Phase 4).

## Notes

- Serialization is the contract every later phase and every reused site depends on. Version the JSON (a `version` or `schema` field in `SceneConfig`) so future shape changes can migrate. Record the chosen JSON shape as a `decision`.
- Report progress via `update_state` (`file_touched`, `commit`, `decision` for the JSON schema/versioning call, `open_thread` for deferred polish).
- If localStorage quota or SSR-hydration of persisted state forces a non-obvious tradeoff, make the safe call (guard `window`, no hydration mismatch) and note it; do not stall.
