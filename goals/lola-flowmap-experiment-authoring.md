---
task: lola-flowmap-experiment-authoring
spec: docs/plans/2026-06-08-server-side-experiments-and-flow-canvas-surface.md
shared_state: [lockfile]
verify: pnpm install && pnpm --filter @lola/web lint && pnpm --filter @lola/web build && pnpm --filter @lola/web flowmap:check
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: author + configure experiments from the app-flow canvas (Phase 4)

Add experiment **authoring** to the `/admin/flow` canvas so an admin can create an experiment on a node, set/adjust the traffic split between variants, and start/stop it : without leaving the canvas. This is Phase 4 (write) building directly on the merged Phase 3 read-only overlay (PR #240). Read the Phase 3 code first: `apps/api/src/modules/admin/experiments/*` (the admin-gated proxy) and `packages/flowmap/src/react/*` (the overlay UI: `experiments.ts`, `experiment-badge.tsx`, `flow-canvas.tsx`, `screen-node.tsx`).

## Context
- Phase 3 already gives you: an admin-gated server proxy (`JwtAuthGuard + AdminGuard`) that lists experiments + results using `LUMITRA_ANALYTICS_*` server-side (key never reaches the client), and a read-only overlay badging nodes via `targeting.nodeRef`.
- Lumitra write API (project key, `X-API-Key`, server-side only):
  - `POST /api/projects/{pid}/experiments` (create: key, name, variants:[{key,weight}], targeting)
  - `POST .../experiments/{id}/goals` (add goal)
  - `POST .../experiments/{id}/start` and `/stop`
  - flags PATCH for rollout exists too, but this task is experiments only.

## Scope (build exactly this)
1. **Extend the admin proxy with write endpoints** (same controller/module, same `JwtAuthGuard + AdminGuard`, key stays server-side):
   - create experiment (body: key, name, variants with weights, optional goal; set `targeting.nodeRef` to the node the admin created it on),
   - update variant weights (re-create/patch per what the Lumitra API supports : if there is no update-variants endpoint, surface that as a known limitation rather than faking it),
   - start, stop.
   Validate inputs (weights are integers summing to 100; key matches `^[a-z0-9_-]+$`). Return the same compact, browser-safe shape as Phase 3 (no key).
2. **Canvas authoring UI** on `/admin/flow` (extend the Phase 3 overlay, do not rewrite it):
   - On a node with no experiment: a "Create experiment" affordance (form: name, 2 variants with a weight split slider/inputs defaulting 50/50, optional primary goal). On submit it POSTs through the proxy with `targeting.nodeRef` = that node's ref.
   - On a node with an experiment: show + edit the **traffic split** (the core ask), and start/stop controls reflecting status. Optimistic UI with error rollback.
3. Keep the read-only overlay behavior intact when authoring is not in use.

## Out of scope
- No changes to the story pipeline, analytics-node, or the Lumitra platform code. No flag authoring (experiments only). No bulk/cross-project ops. No new product-facing (non-admin) surface.

## Constraints
- All write endpoints admin-gated; the Lumitra API key must NEVER reach the browser (assert in tests, mirroring Phase 3).
- If you add API routes, run `pnpm --filter @lola/web flowmap:gen` (build first, then gen) and commit the regenerated `flowmap*.json` (drift gate is in verify + CI).
- TDD for the write proxy endpoints (mock Lumitra HTTP; assert validation + admin gate + no key leak).
- NEVER use em-dashes or en-dashes. Conventional commits.

## Escalate (stop and ask) when
- The Lumitra API lacks a clean way to update an existing experiment's variant weights (changing weights mid-run is a real product question : surface it, do not invent a destructive recreate that loses results).
- The authoring UX has a genuinely ambiguous fork (e.g. what happens to in-flight assignments when weights change) that is a product decision.
- Anything would write outside the experiments API, touch the pipeline, or another repo.

## Definition of done
- Admin can create an experiment on a flow node, set the traffic split, and start/stop it, entirely from `/admin/flow`, with the key server-side and admin-gated.
- Validation + tests (incl. no-key-leak) pass; `pnpm --filter @lola/web build` + `lint` + `flowmap:check` green (flowmap regenerated if routes added).
- Phase 3 read-only behavior preserved.
