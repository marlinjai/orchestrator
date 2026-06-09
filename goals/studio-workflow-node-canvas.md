---
task: studio-workflow-node-canvas
spec: src/app/workflows
depends_on: [studio-workflow-workspace-id]
shared_state: [lockfile]
verify: pnpm test
verify_fix_cap: 3
verify_timeout_s: 1800
---

# Goal

Build the generation-workflow node canvas v1: a read-only Studio UI that renders a `WorkflowDefinition` as a visual node graph and overlays live run status. This is the "canvas is a live view of the engine" surface from the architecture (the engine is the code-driven source of truth; this just views it). v1 is READ-ONLY (no editing, no authoring): list -> render the DAG -> show a run's node statuses.

## Read first

- The workflow engine API in `@marlinjai/lumitra-core/workflow` (package dir `packages/lumitra-core/src/workflow/`): `listWorkflows()`, `getWorkflow(id)`, `WorkflowDefinition`/`WorkflowNode` types, `nodeDependencies(node)` (gives a node's upstream deps -> the edges), `entryNodes()`. The graph structure comes entirely from here; do not re-derive it.
- The run API (landed by the dependency task `studio-workflow-workspace-id`): `GET /api/v1/workflows/runs/:id` returns the run + per-node-run status (`pending|running|succeeded|failed`) + rolled cost. This is the live overlay source.
- `src/app/canvas/` (the EXISTING 3D scene composer) for the app's page/layout/styling conventions (Tailwind 4, the auth gate, data fetching). Mirror its conventions; do NOT modify it.
- `src/app/api/v1/workflows/` for the run/runs route shapes.

## Definition of done

1. **Add `@xyflow/react`** (React Flow, React-19 compatible) as a dependency. It is the node-graph renderer. (This is the only new dep; it is why `shared_state: lockfile`.)
2. **Routes (read-only):**
   - `src/app/workflows/page.tsx`: lists the registered workflows via `listWorkflows()` (id, label, node count). Each links to its canvas.
   - `src/app/workflows/[id]/page.tsx` (+ a client component): loads `getWorkflow(id)` and renders it as a React Flow graph. Nodes = `WorkflowNode`s (show id, `method`, `model`). Edges = derived from each node's `nodeDependencies()` / `ref` bindings (an edge from each upstream dep to the node). Provide a simple deterministic left-to-right layout by topological depth (compute depth from `nodeDependencies`; do NOT add a heavyweight layout dep like dagre/elk for v1).
3. **Live run overlay:** if the canvas page receives a `?runId=<id>` query param, poll `GET /api/v1/workflows/runs/:id` (e.g. every ~2s while the run is not complete) and color each node by its node-run status (pending / running / succeeded / failed), and show the rolled `totalCostUsd`. When `isRunComplete`, stop polling. With no `runId`, just show the static definition.
4. **Auth + access:** respect the studio's existing auth gate (mirror `src/app/canvas`). Do not invent a new auth path.
5. **Component tests (the verify gate):** add Testing-Library + vitest tests that render the canvas client component with a mock `WorkflowDefinition` and assert the right nodes + edges render, and that node colors reflect a mock run-status payload. `pnpm test` (the infisical-wrapped suite) must be GREEN.
6. Single conventional-commit on this branch.

## Constraints

- READ-ONLY v1. No node editing, no drag-to-connect authoring, no save. Those are later slices. (React Flow renders read-only; disable interactive connect/edit.)
- Do NOT change the workflow engine (`@marlinjai/lumitra-core/workflow`), the run API, or the existing `src/app/canvas` (the 3D composer). You CONSUME them.
- Do NOT add a graph-layout library; a simple topological-depth column layout in code is the v1 requirement.
- Keep it single-repo (this studio app). Do not push to any remote. When done, output a final completion message.

## Notes

- The whole value is "see the DAG, watch a run light up." Keep the surface minimal and correct: a clean React Flow render of the real definition + a polled status overlay. Polish (zoom-to-fit, minimap) is fine if cheap via React Flow built-ins, but not required.
- If the run API shape differs from what this goal assumed (the dependency task may have adjusted it), read the actual route and match it; the route is the source of truth.
