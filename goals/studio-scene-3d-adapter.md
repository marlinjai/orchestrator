---
task: studio-scene-3d-adapter
spec: docs/specs/2026-06-26-scene-3d-adapter-u4.md
shared_state: [lockfile, workspace]
verify: pnpm db:generate && pnpm -r --filter './packages/*' build && pnpm test && npx tsc --noEmit && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Implement the leaf spec at `docs/specs/2026-06-26-scene-3d-adapter-u4.md` (already committed in this worktree, status: decided). Build the Phase U4 "pure 3D render adapter": render a `@marlinjai/studio-scene-core` `Scene` (a SceneNode tree of camera + lights + meshes) in a React Three Fiber canvas inside the Studio app, with a reconciled working colorspace and orbit controls, on a new `/scene` page. NO FX EffectComposer bridge in v1, NO cross-repo `@marlinjai/lumitra-fx` dependency. Read the spec IN FULL first; it is the source of truth.

## IMPORTANT: this is a RENDER slice

The verify gate (test + tsc + lint + next build) proves the code COMPILES and the schema round-trips, but it CANNOT prove the 3D scene actually renders correctly (a mesh could be invisible, the camera mispointed, the colorspace wrong). So:
- Make the code correct and the `/scene` fixture render a visible, lit box (plus a GLB if a Model3D asset exists). Add a tiny readiness affordance the operator can screenshot.
- Do NOT claim the visual is verified; the operator does the visual check. Your job is green build + correct, reviewable code.

## Read first

- `docs/specs/2026-06-26-scene-3d-adapter-u4.md` (full design)
- `packages/studio-scene-core/src/{node.ts,param.ts,scene.ts,registry.ts,serialize.ts,fx-nodes.ts,index.ts}` (the SceneNode/Scene model, `registerNode`, the param spec system, and how fx-nodes register; mirror that pattern for the 3D nodes)
- `src/components/studio/Asset3DPreview.tsx` (the existing R3F single-GLB preview from Phase 1: the Canvas setup, `useGLTF`, OrbitControls, lighting and colorspace already in use; reuse its proven patterns)
- `src/app/canvas/page.tsx` and `src/components/canvas/MercuryScene.tsx` (existing R3F usage in the app)
- `src/lib/asset/sign.ts` + `src/lib/asset/repository.ts` (how a Model3D asset resolves to a signed Storage Brain GLB url, for the assetRef resolver)
- root `package.json` + `pnpm-workspace.yaml` (you will add `"@marlinjai/studio-scene-core": "workspace:*"` to the app deps)

## Definition of done (per the spec)

1. **3D node definitions in scene-core.** Add `scene.camera`, `scene.light`, `scene.mesh` node types via `registerNode` in a new `packages/studio-scene-core/src/scene-nodes.ts` (mirroring `fx-nodes.ts`), imported for side-effect from `index.ts`. Param specs: camera (`fov`, `near`, `far`), light (`kind`: ambient|directional|point, `intensity`, `color`), mesh (`geometry`: box|sphere|plane|gltf, `color`; `assetRef` carries the Model3D id when `geometry: gltf`). Each carries correct `kind`/`allowsTransform` (these 3D nodes DO allow a transform, unlike fx.*) and registry legality. Bump scene-core to 0.2.0. Golden round-trip + registry-legality tests for the new types.
2. **Link scene-core into the app** as `"@marlinjai/studio-scene-core": "workspace:*"` (root `package.json`); `pnpm install` to relink (commit the lockfile change).
3. **The renderer** (`src/components/scene3d/SceneRenderer.tsx` + a `nodeToR3F` mapping): a React Three Fiber `<Canvas>` with reconciled colorspace (linear working space, sRGB output, `ACESFilmicToneMapping`), `OrbitControls`, that walks a `Scene.root` tree and renders each node by type (camera -> `PerspectiveCamera`, light -> the right light, mesh -> primitive geometry or a `useGLTF` GLB resolved via an injected `resolveAsset(assetId) => Promise<url>` callback). Honors each node's `transform`. A `scene.mesh` with `geometry: gltf` but an unresolved asset falls back to a placeholder box (never a blank canvas).
4. **The `/scene` page** (`src/app/scene/page.tsx`): renders a FIXTURE Scene (a camera, an ambient + a directional light, one primitive box mesh, and, if the project has a Model3D asset, one gltf mesh) through `SceneRenderer`, with orbit controls. Server-resolves the asset url via the asset repository for the resolver. Add a small `data-scene-ready` marker the operator can screenshot.
5. **Tests:** the 3D node types register + validate + round-trip (values-only, byte-identical) in scene-core; `nodeToR3F` maps each node type to the expected element (component test with the canvas mocked, mirroring the existing R3F spec pattern); the assetRef resolver path (resolved url -> gltf, unresolved -> placeholder box).

## Constraints

- NO FX EffectComposer / `@react-three/postprocessing` bridge, NO dependency on `@marlinjai/lumitra-fx` (v1 is pure 3D; the FX overlay is a later phase).
- NO new npm dependencies: `three`, `@react-three/fiber`, `@react-three/drei` are already present; use them.
- Keep scene-core RENDER-FREE: the 3D node DEFINITIONS (param specs, legality) go in scene-core; the R3F RENDER stays in the app (`src/components/scene3d/`). scene-core must not import three / @react-three.
- No Prisma migration. No em-dashes or en-dashes anywhere.
- Make a SINGLE conventional commit on this branch describing the WHY. Do NOT push or merge. When done, output a final message that the task is complete.
