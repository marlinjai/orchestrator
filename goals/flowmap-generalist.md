---
task: flowmap-generalist
spec: docs/plans/2026-05-31-flowmap-next-phases-handover.md (Slice C)
depends_on: [flowmap-thumbs-storage-brain]
---

# Goal

Implement Slice C of the flowmap-next handover: prove `@lola/flowmap` is a generalist by (C1) generating a flowmap for `apps/landing` with ZERO new package code, and (C2) adding a NestJS endpoint-explorer adapter so `apps/api` controllers become endpoint nodes on the map. The package must stay app-agnostic the whole way.

## Read first

- `packages/flowmap/src/*`: the model, `nextAppRouter`, `mergeFlowMaps`, and the `./core` / `./next` / `./xstate` / `./react` entry points. Understand the FlowMap node/edge shape and that the model already supports multi-platform merges.
- `apps/web/scripts/generate-flowmap.ts`: the reference generator wiring (`nextAppRouter` over `apps/web/src/app`, annotations, output to `public/flowmap.json`).
- `apps/web/flowmap.annotations.ts`: the annotation shape.
- `apps/landing/src/app/[locale]/*`: the landing App Router tree (home, demo, join, privacy, impressum, partners; plus `api/waitlist`, `api/contact`).
- `apps/api/src/modules/*/*.controller.ts`: the controller decorator grammar you will parse with ts-morph.
- Confirm `ts-morph` is already a dependency of `packages/flowmap` (the handover says it is); if it is in `apps/web` only, wire it into the package properly.

## Scope and changes

### C1. apps/landing board (no package changes)

- Add `apps/landing/flowmap.config.ts` (or a script mirroring `generate-flowmap.ts`) pointing `nextAppRouter` at `appDir = apps/landing/src/app`, with `repoRoot` and `defaultLocale: 'de'`. Produce a landing `flowmap.json`. NO changes to the package for C1.
- Surface it: either a new `/admin/flow?app=landing` query param that loads the landing map, or a second board. Keep `/admin` locale-free.

### C2. NestJS endpoint explorer (new package adapter)

- New `packages/flowmap/src/nest/` adapter exporting `nestRouterExplorer`, using **ts-morph** over `apps/api/src/modules/*/*.controller.ts`. Do NOT use Nest's runtime RouterExplorer (it needs the DI container: slow, test-hostile).
- Decorator grammar: class `@Controller('families/:familyId/stories')` + method `@Get(':id')` / `@Post(...)` / `@Patch` / `@Delete`; label from `@ApiOperation({ summary })`. Final route = controllerPath + methodPath (normalize slashes).
- Emit nodes shaped like: `{ id: 'api:endpoint:POST:/families/:id/bootstrap-self', kind: 'endpoint', platform: 'api', route, label, file, domain: <module>, meta: { httpMethod, guards } }`.
- Co-locate unit tests in `packages/flowmap` (a fixture controller + assertions on the parsed nodes). This is the main correctness surface for C2.
- HTTP edges (screen -> endpoint) are OPTIONAL and a SECOND step: the web ts-morph edge pass could be extended to capture `apiClient.fetch('/path', ...)` calls and emit `http` edges into the endpoint nodes. Land the endpoint nodes first; only add edges if time allows, else file an `open_thread`.

### Combined map

- The generator merges web + landing + api node/edge sets via the existing `mergeFlowMaps` (the model already supports multi-platform). One board for the whole system, or selectable via the `app` query param. Do not regress the existing web board.

## Definition of done

- A landing `flowmap.json` is produced and renders on `/admin/flow?app=landing` (or the second board).
- The nest adapter emits endpoint nodes with correct routes for a representative controller; unit tests in `packages/flowmap` are green.
- `pnpm --filter @lola/flowmap test` (or the package's test task) passes.
- `pnpm --filter @lola/flowmap build` clean; `pnpm --filter @lola/web exec tsc --noEmit` clean; landing typecheck clean if you add a config/script there.
- The existing `/admin/flow` web board still works (no regression).
- Conventional-commit(s), subject lowercase after the colon, e.g. `feat(flowmap): nest endpoint explorer + landing board (generalist proof)`.

## Constraints

- Stay in this worktree. Do not push. Operator handles push + PR + merge.
- Keep `@lola/flowmap` app-agnostic: the nest adapter parses source paths passed IN (glob/dir args), it must not hardcode lola paths. The `apps/web` / `apps/landing` generators pass the lola-specific dirs.
- No em-dashes or en-dashes. Use colons, parentheses, commas, periods.
- `/admin` is locale-free: do not route to it via the i18n navigation helper.
- This is the largest, optional slice. If you cannot land BOTH C1 and C2 cleanly within budget, land C2 (the endpoint explorer + tests, the higher-value generalist proof) fully and file C1 or the HTTP-edge step as `open_thread` entries rather than leaving a half-built board.

## Notes

- `pnpm install` the worktree, then `pnpm --filter @lola/flowmap build` before the generators import it.
- `./react` ships as source (transpiled by web); `./core`/`./next`/`./xstate`/(new) `./nest` compile to `dist`. Add the new `./nest` export to the package's build + exports map consistently with the others.
- If anything contradicts repo conventions, prefer the conventions and record it via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message that Slice C is complete, naming the new `./nest` export, the landing config/board, and any `open_thread` deferrals.
