---
task: lola-writer-experiment-wiring
spec: docs/plans/2026-06-08-server-side-experiments-and-flow-canvas-surface.md
shared_state: [lockfile]
verify: pnpm install && pnpm --filter @lola/api db:generate && pnpm --filter @lola/api test && pnpm --filter @lola/api build
verify_fix_cap: 2
verify_timeout_s: 1500
---

# Goal: wire the first server-side writer experiment into lola-stories (NestJS API)

Instrument the story-generation pipeline so the **writer model is chosen by a Lumitra experiment** and per-generation metrics are emitted to Lumitra, using the just-published `@marlinjai/analytics-node` server SDK. This is the first real consumer of the server-side experiments work (analytics-platform #12). Work in `apps/api` only.

## Hard rule (non-negotiable)
Analytics must NEVER break or slow story generation. If analytics is unconfigured, errors, or times out, the pipeline runs **exactly as today** (writer on `claude-sonnet-4-6`, no variant, no emit) and the generation still succeeds. Wrap every analytics call in defensive try/catch with a short timeout; failures are logged and swallowed, never thrown into the generation path.

## Scope (build exactly this)

1. **Add the dependency**: `pnpm add @marlinjai/analytics-node --filter @lola/api` (pulls `@marlinjai/analytics-core`). Pin a published semver range (e.g. `^1.0.0`), not `workspace:*`.

2. **AnalyticsExperimentService** (new, in `apps/api/src/modules/llm/` or a small `analytics` module): initializes `analytics-node` from env and exposes:
   - `getWriterModel(unitId: string): Promise<string>` -> resolves the `writer-model` experiment variant for `unitId`; maps `control -> 'claude-sonnet-4-6'`, `treatment -> 'claude-opus-4-8'`; returns the default `'claude-sonnet-4-6'` when analytics is disabled/unconfigured/errors or no variant.
   - `trackGeneration(unitId, { experimentKey, variant, properties })` -> fires the events (see #4), swallowing all errors.
   - It reads config from env: `LUMITRA_ANALYTICS_PROJECT_ID`, `LUMITRA_ANALYTICS_API_KEY`, `LUMITRA_ANALYTICS_INGEST_URL` (e.g. `https://analytics.lumitra.co/api/ingest`). If any is missing, the service is a no-op that returns defaults (analytics disabled).

3. **Variant-driven writer model**: in `StoryPipelineV2Service` (the writer stage uses `QUALITY_MODEL`), make the writer (and only the writer) model come from `getWriterModel(familyId)` instead of the hardcoded constant, defaulting to `claude-sonnet-4-6`. The `familyId` is the assignment unit (stable, cross-device). Thread it from the caller (the stories service knows the familyId). Do NOT change the critic model or the FAST_MODEL. Do NOT change writer behavior otherwise (the two-call prose+segment architecture from #237 stays intact).

4. **Emit metrics** after a generation completes (success path), via `trackGeneration`, tagged with `experiment_id`/`variant`/`unitId=familyId`:
   - a `story_generated` custom event with properties: `latencyMs` (total) + per-stage timings if available, `wordCount`, `fallbackUsed` (bool: did segmentation fall back to single-narrator), `model`, `mode`, `language`.
   - a binary goal event `generated_without_fallback` (fires only when `fallbackUsed === false`) so the dashboard's conversion stats have a yes/no signal.

5. **Config plumbing**: add the three `LUMITRA_ANALYTICS_*` env vars to the api config/validation (matching how existing env is validated) with the analytics-disabled default. Document them in the relevant `.env.example`/config doc. Do NOT hardcode secrets.

## Out of scope (do NOT do)
- Do NOT create the experiment in Lumitra (that is an ops action: dashboard/API). Assume an experiment keyed `writer-model` with variants `control`/`treatment` may or may not exist; the code must work either way.
- Do NOT set any Infisical secrets (Marlin populates `LUMITRA_ANALYTICS_*` in `/apps/api`).
- No server->client propagation, no flow-canvas, no continuous-metric statistics, no web/client changes.
- Do NOT modify the writer's prose/segmentation logic, the critic, or `syncSpeakerParts`.

## Constraints
- TDD: tests first. Cover: variant `treatment` -> opus, `control`/disabled/error -> sonnet default; `story_generated` + goal events emitted with correct tags on success; **analytics-disabled and analytics-throwing paths are no-ops that do not affect the returned story**; familyId is the unit id.
- Mock `@marlinjai/analytics-node` in tests (do not hit the network).
- NEVER use em-dashes or en-dashes (code, comments, commits). Use colons/commas/parentheses.
- Conventional commits (commitlint + husky).

## Escalate (stop and ask) when
- Threading `familyId` into the writer requires changing the #237 two-call writer behavior in a risky way.
- `@marlinjai/analytics-node`'s actual API surface differs from the assumed `init`/`getVariant`/`track` shape (inspect the installed package first; adapt; only escalate if it cannot support this use).
- Anything would touch the web app, another repo, or require a migration.

## Definition of done
- `apps/api` depends on `@marlinjai/analytics-node` (published semver).
- Writer model is variant-driven via `getWriterModel(familyId)`, defaulting to `claude-sonnet-4-6`, with analytics fully optional + non-breaking.
- `story_generated` + `generated_without_fallback` events are emitted on success with experiment/variant/unit tags.
- Tests prove the variant mapping AND the analytics-disabled/throwing no-op safety.
- `pnpm --filter @lola/api test` + `build` green; existing tests pass.
