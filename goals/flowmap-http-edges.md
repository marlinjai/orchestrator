---
task: flowmap-http-edges
spec: docs/plans/2026-05-31-flowmap-next-phases-handover.md (Slice C deferred: HTTP edges)
---

# Goal

Implement the deferred "HTTP edges" follow-up from the flowmap generalist work. Today the `/admin/flow` canvas has three SEPARATE boards (`?app=web|landing|api`); the api board (120 endpoint nodes from `@lola/flowmap/nest`) is a set of ISLANDS because the nest adapter returns no edges (endpoints get called, they do not navigate). This slice derives cross-platform `http` edges (a web/landing SCREEN node -> the api ENDPOINT node it calls) via a ts-morph pass over `apiClient` call sites, and surfaces them on a NEW combined "system" board so they are structurally valid and visible.

`@lola/flowmap` and `./react` must stay app-agnostic: the new edge derivation lives in the package but takes the call-site source files and the endpoint route table as INPUTS (passed by the host generator). No hardcoded lola paths inside the package.

## Read first

- `packages/flowmap/src/next/edges.ts` (the existing `deriveNextEdges` ts-morph pass: how it classifies string/template/conditional targets, peels `/[locale]`, builds edge ids, and emits the `UnresolvedEdge` report). Mirror its conventions and reuse its helpers where possible.
- `packages/flowmap/src/nest/nodes.ts` (the endpoint node-id scheme you must match against: `makeNodeId('api','endpoint', `${httpMethod}:${route}`)`, route = `joinRoute(apiPrefix, controllerPath, methodPath)`, apiPrefix `api/v1`, params look like `:familyId` from the Nest decorators).
- `packages/flowmap/src/model.ts` (the `FlowEdge` shape + edge `kind` union + `makeNodeId` + `validateFlowMap`: add a `'http'` edge kind if not present; make sure `validateFlowMap` does NOT reject an edge whose `from`/`to` cross platforms).
- `packages/flowmap/src/build.ts` and the `mergeFlowMaps` helper (how node/edge sets compose; the combined board is a merge).
- `apps/web/src/lib/api-client.ts` (THE crux: learn exactly how the app calls the API. Is it `apiClient.fetch('/path', {method})`, or `apiClient.get/post/patch/delete('/path')`? Does the path passed by callers already include the `/api/v1` prefix, or does the client prepend a base URL? You must know this to normalize call paths to endpoint routes).
- `apps/web/scripts/generate-flowmap.ts` (writes 3 maps today: `buildFlowmapMap` web, `buildLandingFlowmapMap`, `buildApiFlowmapMap`. You will add a 4th combined "system" map).
- `apps/web/scripts/check-flowmap.ts` (the drift gate; it gates all boards via a `BOARDS` array. Add the new system board).
- `apps/web/src/app/admin/flow/flow-client.tsx` (the `?app=web|landing|api` switcher; add a `system` option and its source file).

## Scope and changes

### 1. The http-edge derivation (package, app-agnostic)

- New `packages/flowmap/src/next/http-edges.ts` (or extend `edges.ts` if cleaner) exporting e.g. `deriveHttpEdges({ callSiteFiles, screenNodes, endpointNodes, repoRoot })`. Co-located unit tests (`*.test.ts`) over fixture call sites + fixture endpoint nodes.
- Walk `callSiteFiles` with ts-morph. Find `apiClient.*(...)` call expressions (the exact method names + signature you learned from `api-client.ts`). For each, extract the path argument (string literal or template) and the HTTP method (from the wrapper name like `.post(...)`, or a `{ method: 'POST' }` option, defaulting per the client's convention).
- Attribute each call site to the SCREEN node that contains it (same file-path -> screen-node attribution the existing edge pass already does; reuse it).
- **Path matching (the hard part) - be conservative:** normalize both sides to a canonical pattern and match on (method, static-segment structure):
  - Apply the same `/api/v1` prefix handling the client uses (prepend it to caller paths if the client does, so both sides are `/api/v1/...`).
  - Replace every DYNAMIC segment with a single wildcard token on BOTH sides: a Nest `:param` and a JS template `${...}` interpolation both become the same placeholder (e.g. `:*`). Do NOT try to match param NAMES (web `${child.id}` vs Nest `:id` will not match by name).
  - Match a call to an endpoint when method matches AND the wildcarded path patterns are equal AND segment counts match. Emit a `kind: 'http'` `FlowEdge` from the screen node id to that endpoint node id.
  - If a call cannot be confidently matched (non-literal path, ambiguous, no method, multiple endpoint matches), DO NOT force it: add an `UnresolvedEdge`-style entry (same report shape the existing pass uses) so it shows up in the generator's warning, exactly like the existing unresolved-edge handling. Conservative-but-correct beats many wrong edges.

### 2. The combined "system" board (apps/web generator)

- Add `buildSystemFlowmapMap()` to `generate-flowmap.ts`: build web + landing + api structural maps, `mergeFlowMaps` their node/edge sets, then run `deriveHttpEdges` (passing the merged screen nodes + the api endpoint nodes + the web/landing call-site files) and append the `http` edges. Sort deterministically like the other boards (nodes by route then id, edges by id). Write `apps/web/public/flowmap.system.json`.
- This is the ONLY board that contains cross-platform `http` edges. The per-app web/landing/api boards stay exactly as they are (do not add http edges to them; their endpoint targets would dangle).

### 3. Canvas + drift gate wiring (apps/web)

- `flow-client.tsx`: add a `system` entry to `FlowApp` / `APP_LABELS` / `APP_SOURCES` (`/flowmap.system.json`, label e.g. `system (all + api calls)`). Keep `/admin` locale-free (read `?app` off `window.location`, as today). The `http` edges should render visibly distinct from navigation edges (e.g. a dashed/colored edge); reuse any edge-kind styling the canvas already has, or add minimal styling for `kind: 'http'`.
- `check-flowmap.ts`: add the system board to the `BOARDS` array so `flowmap:check` gates `flowmap.system.json` too. It must regenerate deterministically and pass on a clean tree.

## Definition of done

- `pnpm --filter @lola/flowmap test` passes, including new http-edge unit tests (fixture call sites -> expected edges + expected unresolved entries).
- `pnpm --filter @lola/flowmap build` clean; `pnpm --filter @lola/web exec tsc --noEmit` clean.
- `pnpm --filter @lola/web flowmap:gen` writes `flowmap.system.json` (web+landing+api nodes + `http` edges); the per-app boards are byte-stable except `generatedAt`.
- `pnpm --filter @lola/web flowmap:check` passes all FOUR boards on a clean tree; a negative test (remove a node from `flowmap.system.json`) fails it.
- The new board renders at `/admin/flow?app=system` with http edges visible and distinct; the existing web/landing/api boards are unchanged.
- The generator logs how many `http` edges resolved and how many call sites were left unresolved (no silent truncation).
- Conventional-commit(s), subject lowercase after the colon, e.g. `feat(flowmap): derive http screen-to-endpoint edges + system board`.

## Constraints

- Stay in this worktree. Do not push. Operator handles push + PR + merge.
- Keep `@lola/flowmap` app-agnostic: `deriveHttpEdges` takes files + nodes as inputs; the lola-specific globbing (which files are call sites, the `api/v1` prefix) is decided by `apps/web/scripts/generate-flowmap.ts`, not the package.
- No em-dashes or en-dashes anywhere. Use colons, parentheses, commas, periods.
- `/admin` is locale-free: do not route to it via the i18n navigation helper.
- Conservative matching: an unresolved entry is ALWAYS better than a wrong edge. Do not invent param-name matches.

## Notes

- `pnpm install` the worktree, then `pnpm --filter @lola/flowmap build` before the web generator imports it. `./react` ships as source (transpiled by web); `./core`/`./next`/`./xstate`/`./nest` compile to `dist`.
- This needs NO database and NO migration (pure static analysis + generated JSON). Tests mock nothing DB-related.
- Commitlint: lowercase subject after the colon. The repo squash-merges; a Marlin-authored PR needs no bridge commit.
- If anything contradicts the codebase reality you find (e.g. apiClient has a different call shape than assumed, or `mergeFlowMaps` does not exist by that name), prefer the codebase and record the deviation via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message naming: the new `deriveHttpEdges` export + tests, the system board file, the resolved/unresolved edge counts, and the switcher + drift-gate wiring.
