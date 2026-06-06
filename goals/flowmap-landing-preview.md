---
task: flowmap-landing-preview
spec: docs/plans/2026-05-31-flowmap-next-phases-handover.md (Slice C deferred: landing preview, Option C)
---

# Goal

Implement the deferred "landing live preview" follow-up, chosen approach = Option C: landing nodes on the `/admin/flow` board get (1) a real screenshot thumbnail on the card (captured by the existing Playwright script pointed at the landing origin, stored in Storage Brain like web thumbnails), and (2) an "Open live" action that opens the real landing URL in a NEW TAB (no embedded iframe, no proxy). This sidesteps the cross-origin iframe problem entirely: landing is 6 public static pages, so a screenshot + one-click open is the right fidelity. The same-origin embedded live preview for WEB nodes stays exactly as it is.

`@lola/flowmap` and `./react` MUST stay app-agnostic. The package learns "this node opens externally" via an injected prop; the web app decides the landing base URL. No landing/lola URL is hardcoded in the package, and NO runtime URL is baked into any committed `flowmap.*.json` (compose it at runtime so the drift gate stays stable).

## Read first

- `packages/flowmap/src/react/screen-node.tsx`: the `ScreenNode` + `LivePanel`. Today a focused node with `preview.live` blooms into a SAME-ORIGIN iframe (web). You will add an external-open path. Note the existing app-agnostic props `resolveThumbnailUrl` and `onCaptureThumbnail`.
- `packages/flowmap/src/react/flow-canvas.tsx` + `react/index.tsx`: where `FlowCanvasProps` are declared and forwarded to nodes.
- `packages/flowmap/src/model.ts`: `FlowNode` has `platform` ('web' | 'landing' | 'api') and `route`. Use these; do not add new committed fields for this.
- `apps/web/src/app/admin/flow/flow-client.tsx`: the host. It wires `resolveThumbnailUrl` / `onCaptureThumbnail` and the `?app=` switcher. You will add the external-URL resolver here.
- `apps/web/scripts/capture-flowmap-shots.ts`: the Playwright capture script (Slice A: logs in as seed admin, screenshots web routes same-origin, sharp -> webp, uploads to `POST /api/v1/admin/flowmap/node-thumbnails/:nodeId`). You will add a landing mode.
- `apps/web/scripts/generate-flowmap.ts` + `apps/web/public/flowmap.landing.json` + `flowmap.system.json`: to confirm landing node `route` values (e.g. `/[locale]`, `/[locale]/demo`).
- `apps/web/src/config` env validation (how `NEXT_PUBLIC_*` env is validated/consumed), and the marketplace slice pattern for "env var is operational, referenced via validated env, documented for Infisical, never hardcoded".

## Scope and changes

### 1. Package: an external-open path (app-agnostic)

- Add an optional prop, threaded through `FlowCanvas` -> `ScreenNode`/`LivePanel`:
  `resolveExternalUrl?(node: FlowNode): string | null` (returns an absolute URL when the node should open in a new tab, else null).
- Behavior in `ScreenNode`/`LivePanel`:
  - If `resolveExternalUrl(node)` returns a URL, the focused node shows an "Open live" action (an explicit button/link) that opens it via `window.open(url, '_blank', 'noopener,noreferrer')`. Do NOT embed an iframe for these nodes, and do NOT show the html-to-image "Update thumbnail" button (capture is Playwright-only for them).
  - If it returns null (or the prop is absent), behavior is UNCHANGED: same-origin `preview.live` still blooms into the embedded iframe with capture (web nodes).
- Keep it generic: the package does not know what "landing" means; it just calls the resolver. Add/adjust co-located tests for the branch (external vs embed).

### 2. Web host: supply the landing URL + wire open-in-tab

- In `flow-client.tsx`, implement `resolveExternalUrl(node)`:
  - `platform === 'landing'` -> `${LANDING_BASE}${node.route.replace('/[locale]', '/' + DEFAULT_LOCALE)}` (DEFAULT_LOCALE = 'de'); also strip/skip a bare `/[locale]` root sensibly (it maps to `${LANDING_BASE}/de`).
  - `platform === 'api'` -> null (endpoints are not pages; no preview).
  - `platform === 'web'` -> null (keep the existing same-origin embed path).
- `LANDING_BASE` comes from `process.env.NEXT_PUBLIC_LANDING_URL` with a localhost dev default (e.g. `http://localhost:3000`; verify the landing dev port from the root `dev` turbo task / landing package scripts and use the real one). Do NOT hardcode a guessed prod domain: reference the env var, default to localhost for dev, and document in the PR that `NEXT_PUBLIC_LANDING_URL` must be set to the deployed landing origin in Infisical for prod (envs come from Infisical, never Vercel-direct).
- This applies on BOTH the `?app=landing` board and the combined `?app=system` board (landing nodes appear on both).

### 3. Capture script: landing mode (public, no auth)

- Extend `capture-flowmap-shots.ts` with a landing mode (e.g. `--app=landing`, default stays `web`): iterate the nodes of `flowmap.landing.json`, navigate to each landing route on the LANDING origin (public pages, NO seed-admin login), screenshot at the Desktop viewport, `sharp` -> webp, upload to the A1 endpoint keyed by the landing node id with `source: 'playwright'`. The landing origin is a flag/env (default the landing dev origin). Keep the web mode behavior identical.
- Running it (manual now, CI later) is operational, same status as the web capture: document BOTH in the script header / PR, do not block on adding a CI job (file an `open_thread` if you want the CI job tracked). Until it is run, landing cards fall back to the label card (the `resolveThumbnailUrl` 404 fallback already handles this), which is acceptable.

## Definition of done

- `pnpm --filter @lola/flowmap test` passes (incl. new tests for the external-open branch); `pnpm --filter @lola/flowmap build` clean.
- `pnpm --filter @lola/web exec tsc --noEmit` clean.
- `pnpm --filter @lola/web flowmap:check` passes all FOUR boards. IMPORTANT: this change must NOT alter the committed `flowmap.*.json` structurally (the open-in-tab URL is composed at runtime from `route` + injected base; do not write `preview.live` or any env URL into the committed maps). If a map does change, regenerate and confirm the gate is green and the change is justified (it should be none beyond `generatedAt`).
- On `/admin/flow?app=landing` (and `?app=system`), a focused landing node shows an "Open live" action that opens the right landing URL in a new tab; web nodes still embed same-origin as before; api endpoint nodes show no preview.
- The capture script supports `--app=landing` against the landing origin without a login.
- Conventional-commit(s), subject lowercase after the colon, e.g. `feat(flowmap): open-in-tab live preview + playwright thumbnails for landing nodes`.

## Constraints

- Stay in this worktree. Do not push. Operator handles push + PR + merge.
- Keep `@lola/flowmap` app-agnostic: the package gets a generic `resolveExternalUrl` prop; all landing/lola specifics (base URL, locale, platform mapping) live in `apps/web`.
- No runtime/env URL committed into any `flowmap.*.json`. Compose at runtime.
- No em-dashes or en-dashes anywhere. Use colons, parentheses, commas, periods.
- `/admin` is locale-free: read any query off `window.location`, do not use the i18n navigation helper.
- `NEXT_PUBLIC_LANDING_URL` is operational: reference it via validated env, default to the landing dev origin, document the Infisical prod need, do not hardcode a prod domain or add it to any Vercel config directly.

## Notes

- `pnpm install` the worktree, then `pnpm --filter @lola/flowmap build` before the web app/generator/scripts import it. No DB, no migration.
- `./react` ships as source (transpiled by web); `./core`/`./next`/`./xstate`/`./nest` compile to `dist`.
- Commitlint: lowercase subject after the colon. The repo squash-merges; a Marlin-authored PR needs no bridge commit.
- If anything contradicts the codebase reality (e.g. landing routes are not `/[locale]`-prefixed, or `platform` is named differently), prefer the codebase and record the deviation via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message naming: the new `resolveExternalUrl` prop + tests, the `flow-client.tsx` wiring + the `NEXT_PUBLIC_LANDING_URL` env it reads, the capture-script landing mode, and confirmation that the committed maps did not change structurally.
