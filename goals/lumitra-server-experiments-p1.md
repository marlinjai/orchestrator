---
task: lumitra-server-experiments-p1
spec: analytics-platform/docs/superpowers/plans/2026-06-08-server-side-experiments-and-flow-canvas-surface.md
shared_state: [lockfile, workspace, migrations]
verify: pnpm install && pnpm test && pnpm -r typecheck
verify_fix_cap: 2
verify_timeout_s: 1500
---

# Goal: Lumitra server-side experiments, Phase 1 (platform-side)

Build the server-side foundation for experiments on the Lumitra analytics platform so backend frameworks can assign variants and emit per-variant events, matching the client tracker's assignment exactly. This is Phase 1 of the plan at `docs/superpowers/plans/2026-06-08-server-side-experiments-and-flow-canvas-surface.md` (read it). This slice is **platform-only** (this repo); the lola-stories consumer wiring is a separate later slice, do NOT touch lola-stories.

## Context (already shipped, reuse, do not rebuild)
The platform already has: experiment + multi-variant flag CRUD, Bayesian (conversion) engine, per-variant heatmap MVs, remote config `GET /api/projects/{id}/config` (60s TTL), the browser tracker `ExperimentManager` with deterministic MurmurHash3 assignment (`packages/tracker/src/experiment.ts` + `hash.ts`), and the `/api/collect` ingest route. ClickHouse events already have `experiment_id` + `variant` columns.

## Scope (build exactly this)

1. **New published package `@marlinjai/analytics-core`** (`packages/core`, runtime-agnostic, zero side effects, `publishConfig.access: public`): the canonical pure deterministic assignment + the experiment/flag config types. Port the MurmurHash3 + bucket-by-weight algorithm from `packages/tracker/src/experiment.ts` and `hash.ts` **byte-for-byte identical** so a server assignment equals the browser tracker's for the same `(experimentKey, unitId)`. Export `assign(experiment, unitId): variantKey | null` and `evaluateFlag(flag, unitId)`. Add unit tests with fixed vectors asserting parity with the tracker's current output (compute expected values from the tracker algorithm; if the tracker has test vectors, reuse them).

2. **New published package `@marlinjai/analytics-node`** (`packages/node`, Node server SDK, `publishConfig.access: public`, depends on `@marlinjai/analytics-core`):
   - `init({ projectId, apiKey, endpoint })`
   - `fetchConfig(projectId)` with an in-process cache (~60s TTL, mirror the existing remote-config TTL)
   - `getVariant(experimentKey, unitId)` / `getFlag(key, unitId)` using analytics-core (NO browser APIs, NO sessionStorage)
   - `track(eventName, { unitId, experimentId?, variant?, properties? })` -> POST to the server-ingest path with the project API key.

3. **Server-ingest path** on the dashboard (`packages/dashboard/src/app/api/collect/route.ts` or a new `/api/ingest/route.ts`): accept events authenticated by the project **API key** (bearer/header), with **no Origin/CORS gating** (server-to-server), requiring an explicit `unitId`, and persist `experiment_id` + `variant` to ClickHouse via the existing event-insert path. Reuse the existing key-auth + ClickHouse insert helpers; do not duplicate them.

## Decisions (pre-resolved, use these, do NOT stall on them)
- `unitId` is supplied by the caller (a stable id like a familyId/userId); the SDK does not invent one.
- Server-ingest auth = project API key on a no-Origin path; trust the caller-supplied `unitId`.
- Do NOT refactor the existing published `tracker` package in this slice (leave it byte-for-byte). analytics-core becomes the canonical source going forward; a follow-up will dedupe the tracker onto it. Keeping the tracker untouched protects existing consumers.
- Continuous-metric statistics (latency/length) are OUT of scope here (later phase). This slice only needs events to land with experiment_id+variant.

## Out of scope (do NOT do)
- No lola-stories changes. No server->client propagation (Phase 2). No flow-canvas work (Phase 3/4). No tracker refactor. No continuous-metric stats. No CORS `allowed_origins` data change (that is a Marlin dashboard action).

## Constraints
- Follow `@marlinjai/<product>-<role>` naming + `"private"` rules in the package-naming standard: published packages are `@marlinjai/analytics-core` / `@marlinjai/analytics-node`, both with `publishConfig.access: public`, no `"private": true`.
- TDD: write tests first; vitest; assignment-parity tests are mandatory.
- NEVER use em-dashes or en-dashes anywhere (code, comments, commit messages). Use colons, commas, parentheses.
- Conventional commits; the repo uses commitlint + husky.
- Keep changes additive; do not break existing package builds or the tracker's public API.

## Escalate (stop and ask the operator) when
- Porting the assignment requires changing the published tracker's surface, or you cannot achieve byte-for-byte assignment parity.
- A ClickHouse or Postgres migration is needed that could affect other tenants on the shared instance.
- The ingest auth model is ambiguous against the existing key-auth code (do not invent a second auth scheme).
- Anything would touch another repo or another tenant's data.

## Definition of done
- `@marlinjai/analytics-core` and `@marlinjai/analytics-node` exist, build, and are tested.
- A unit test proves server `assign()` matches the tracker's assignment for shared vectors.
- The server-ingest route accepts an API-key-authed server event with `unitId` + `experiment_id` + `variant` and inserts it (covered by a route test that mocks the ClickHouse insert).
- `pnpm install && pnpm test && pnpm -r typecheck` is green.
- Existing tests still pass; the tracker package is unchanged.
