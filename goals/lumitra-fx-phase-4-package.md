---
task: lumitra-fx-phase-4-package
spec: docs/plans/2026-05-31-lumitra-fx-engine.md
depends_on: [lumitra-fx-phase-3-depth-editor]
marlin_proxy: live
marlin_proxy_categories:
  merge_after_verify: live
  branch_cleanup: live
  status_fetch: live
---

# Goal

Implement **Phase 4 (Package + reuse)** of the spec at `docs/plans/2026-05-31-lumitra-fx-engine.md`. Extract the engine from `src/fx/` into a workspace package **`@lumitra/fx`** with a clean public API, docs, and a presets gallery, so it is an **owned, reusable studio tool** that drops into other sites (arbosano, scheunerei, future client work). The lumitra-web app must keep working by consuming the package.

## Read first

- The spec, especially §6 Package and API (the public surface: `<LumitraScene config interactive editor />`, the vanilla `createScene(config)` returning `{ mount, destroy, setParam, toJSON }`, `registerLayer(type, definition)`), §5 The editor ("Later" presets gallery), §10 decision 1 (extract to `@lumitra/fx` at Phase 4 — now), §7 roadmap row "4. Package + reuse".
- The repo workspace setup: `pnpm-workspace.yaml` (currently `packages: ["."]`), root `package.json`, `next.config.ts`. You will add a package to the workspace and have the app depend on it.
- The whole **`src/fx/` engine** from Phases 0-3 — this is what you are moving into the package without behavior change.

## Definition of done

Per the roadmap row "4. Package + reuse" (Outcome: "Owned, reusable studio tool"):

1. **Workspace package `@lumitra/fx`**: create it (e.g. `packages/fx/`), add it to `pnpm-workspace.yaml`, give it its own `package.json` (name `@lumitra/fx`, proper `exports`, peerDeps on react / three / r3f / postprocessing / leva so consumers dedupe), and a build that produces consumable output (types included). Move the `src/fx/` engine into the package.
2. **Public API** exactly per §6: the `<LumitraScene config className interactive editor={false} />` React component; the vanilla `createScene(config): { mount(el), destroy(), setParam(layerId, key, value), toJSON() }`; and `registerLayer(type, definition)` for extensibility. Export the core types (`SceneConfig`, `Layer`, `ParamSchema`).
3. **lumitra-web consumes the package**: the app (the v7 hero and any Phase 2/3 demo scenes/presets) imports from `@lumitra/fx` via the workspace dependency, not from a local `src/fx/`. The old `src/fx/` is removed (no duplicate — no-tech-debt rule). The app builds and the hero renders identically.
4. **Docs**: a `packages/fx/README.md` documenting install, the `<LumitraScene>` and `createScene` APIs, the layer registry / how to add an effect, the `SceneConfig` JSON shape, and the perf/a11y guidance from §8. Keep it scannable (headings, a minimal code example per API).
5. **Presets gallery**: ship the Phase 3 presets as part of the package (or a documented export) so other sites can load them; a simple gallery page/route in lumitra-web that renders the presets is acceptable as the demonstration.
6. `pnpm install` resolves the workspace cleanly, `pnpm lint` + `pnpm build` pass at the repo root (both the package and the app). §8 perf/a11y invariants preserved.
7. **Spec frontmatter `status: in-progress` → `status: completed`** (Phase 4 is the end of the roadmap). Optionally add a short "## 11. Build log" noting all five phases landed.
8. Single commit, conventional-commit message describing the WHY (owned reusable package).

## Constraints

- Stay in this worktree; do not push; no files outside it.
- This phase touches workspace topology (`pnpm-workspace.yaml`, root `package.json`, lockfile). Keep the changes minimal and correct; the app must still build. Do not break the existing Next app routes.
- Preserve the public behavior from Phases 0-3 — this is an extraction/repackaging, not a rewrite. No new features beyond what §6 specifies.
- No em-dashes or en-dashes anywhere, commit message included.

## Notes

- The package boundary is a real API contract (other sites will depend on it). Get `exports` and `peerDependencies` right so a consumer doesn't double-bundle three.js. Record the packaging decisions (build tool, exports map) as a `decision`.
- This is the final phase: setting spec `status: completed` is correct here (and only here).
- Report progress via `update_state` (`file_touched`, `commit`, `decision`, `open_thread`).
- **Escalate** genuine product forks (e.g. whether to publish to a registry vs. keep workspace-internal, package naming if `@lumitra/fx` conflicts). Do not guess on anything that affects how external sites will consume this.
