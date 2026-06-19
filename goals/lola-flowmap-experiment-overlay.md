---
task: lola-flowmap-experiment-overlay
spec: docs/plans/2026-06-08-server-side-experiments-and-flow-canvas-surface.md
shared_state: [lockfile]
verify: pnpm install && pnpm --filter @lola/web lint && pnpm --filter @lola/web build && pnpm --filter @lola/web flowmap:check
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: surface Lumitra experiments on the lola app-flow admin canvas (Phase 3, read-only overlay)

Wire experiment **visibility** into the existing `@lola/flowmap` admin canvas (`/admin/flow`) so an admin can see, on the same canvas that already shows every screen + endpoint, which nodes have a Lumitra experiment and how each is performing. This is Phase 3 (read-only) of `docs/plans/2026-06-08-server-side-experiments-and-flow-canvas-surface.md`. **Authoring (create/edit/ramp from the canvas) is Phase 4, OUT of scope here.**

## Context
- The flow canvas lives at `apps/web` route `/admin/flow`, built on `@lola/flowmap`, rendering web routes (screens) and API endpoints as nodes (read `apps/web/src/app/[locale]/.../admin/flow` and the `@lola/flowmap` package to learn the node model first).
- Lumitra experiments API (project keyed; auth header `X-API-Key`):
  - `GET {endpoint}/api/projects/{projectId}/experiments?status=running` -> list
  - `GET {endpoint}/api/projects/{projectId}/experiments/{id}/results` -> Bayesian results (per-variant sessions/conversions/conversionRate/probabilityToBeBest/lift)
- Server-side config already exists in the API as `LUMITRA_ANALYTICS_PROJECT_ID` / `LUMITRA_ANALYTICS_API_KEY` / `LUMITRA_ANALYTICS_INGEST_URL` (added in the writer-wiring slice). The endpoint base is `https://analytics.lumitra.co`.

## Scope (build exactly this)
1. **Server proxy route** (in the NestJS API under `/admin`, or an apps/web server route if that is the established pattern for /admin data : match what /admin/flow already uses): `GET .../admin/experiments` that calls the Lumitra list + results endpoints server-side using `LUMITRA_ANALYTICS_*`, and returns a compact shape `{ experiments: [{ key, name, status, variants:[{key,weight}], nodeRef, results? }] }`. The Lumitra API key MUST stay server-side (never sent to the browser). Admin-auth gate it like other /admin endpoints. If analytics is unconfigured, return an empty list (no error).
2. **Node <-> experiment mapping**: an experiment associates to a flow node via `targeting.nodeRef` (a flow node id / route / endpoint key stored in the experiment's `targeting` JSON). Read it from `targeting`. If absent, the experiment is listed but unattached. Document the convention in a short comment + the plan doc. (The `writer-model` experiment is a server/pipeline experiment; it maps to the story-generation endpoint node : but do NOT hardcode it; drive everything off `targeting.nodeRef`.)
3. **Canvas overlay**: an "Experiments" toggle/layer on `/admin/flow`. When on, nodes that have an attached experiment get a badge showing status (running/paused/draft) + the variant weights; on hover/click, a small panel shows per-variant probability-to-be-best + lift from results. Nodes with no experiment are unchanged. Read-only.

## Out of scope (do NOT do)
- No create/edit/start/stop/ramp from the canvas (Phase 4). No changes to the experiment data model on Lumitra. No writes to the Lumitra API. No changes to the story pipeline, the writer, or analytics-node. No new top-level product features.

## Constraints
- If you add an API route or endpoint, you MUST run `pnpm --filter @lola/web flowmap:gen` and commit the regenerated `apps/web/public/flowmap*.json` (the drift gate `flowmap:check` is in verify and CI; it needs a `next build` first so route handlers are in the manifest : build, then gen). This is the known flowmap gotcha.
- TDD for the proxy route + the mapping/transform logic (mock the Lumitra HTTP calls; assert the key never leaks to the client shape; assert unconfigured -> empty).
- NEVER use em-dashes or en-dashes. Conventional commits (commitlint + husky).
- Keep the key server-side; the browser only ever sees the compact shape.

## Escalate (stop and ask) when
- The node<->experiment mapping model is genuinely ambiguous (e.g. how a server/pipeline experiment like `writer-model` should attach to a canvas node) and you cannot pick a clean, documented convention : this is a product/UX decision.
- The /admin data-fetch pattern is unclear (API route vs web server route) and the two would diverge meaningfully.
- Anything requires writing to Lumitra, changing the pipeline, or touching another repo.

## Definition of done
- A server-side, admin-gated proxy returns experiments + results with the key never exposed client-side.
- `/admin/flow` has a read-only Experiments overlay badging mapped nodes with status + weights + results-on-demand.
- Mapping is driven by `targeting.nodeRef`, documented.
- `pnpm --filter @lola/web build` + `lint` + `flowmap:check` green (flowmap regenerated if a route was added); existing tests pass.
