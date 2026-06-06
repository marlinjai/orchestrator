---
task: flowmap-per-device-screenshots
spec: follow-up to PR #208 (landing preview) and #200 (storage-brain thumbnails)
shared_state: [prisma, migrations]
---

# Goal

Make the `/admin/flow` board show real **per-device screenshots** (phone / tablet / desktop) for EVERY node, including landing nodes. Today the device-frame panel renders a live SAME-ORIGIN iframe, which is why landing (a different origin) shows no in-canvas preview. The fix: capture per-device screenshots with Playwright (which runs its own browser server-side and has NO cross-origin restriction, so it screenshots the landing origin fine), store one screenshot per (node, device), and render the static per-device screenshot in the device frame and on the card. The same-origin live iframe stays as an optional "Go live" toggle for web nodes; landing keeps its "Open live" new-tab action.

`@lola/flowmap` and `./react` MUST stay app-agnostic: the package renders whatever URL the injected resolver returns for a given (nodeId, device); all lola wiring (the admin endpoint, capture) lives in `apps/web` / `apps/api`.

## Read first

- `packages/flowmap/src/react/screen-node.tsx`: the `DEVICES` presets (`phone 390x844`, `tablet 834x1112`, `desktop 1440x900`), the `DeviceToggle`, the `DeviceFrame`, the live-iframe path, the existing `resolveThumbnailUrl(nodeId)` prop + the `<img>` card render, the `onCaptureThumbnail` live-capture handler, and the `resolveExternalUrl` (landing open-in-tab, from #208).
- `packages/flowmap/src/react/flow-canvas.tsx` + `react/index.tsx`: prop declarations + forwarding.
- `apps/api/prisma/schema.prisma`: `FlowmapThumbnail` (currently `nodeId @unique`, one row per node).
- `apps/api/src/modules/admin/flowmap-thumbnail/flowmap-thumbnail.{controller,service}.ts` + their specs: POST/GET `/admin/flowmap/node-thumbnails/:nodeId`.
- `apps/web/scripts/capture-flowmap-shots.ts`: the Playwright capture (currently one `VIEWPORT={1280,800}` shot per node; `--app=web|landing` already exists from #208).
- `apps/web/src/app/admin/flow/flow-client.tsx`: how `resolveThumbnailUrl` / `onCaptureThumbnail` / `resolveExternalUrl` are wired today.

## Scope and changes

### 1. Storage: per-device (apps/api)

- `FlowmapThumbnail`: add `device String` ('phone' | 'tablet' | 'desktop'); replace `nodeId @unique` with `@@unique([nodeId, device])` (one screenshot per node per device). Migration via the per-worktree DB recipe (see Notes). Existing rows (if any in dev) default `device = 'desktop'`.
- Endpoint:
  - `POST /admin/flowmap/node-thumbnails/:nodeId?device=<d>&source=<s>` (device required + validated against the three; reject others with 400). Upsert by (nodeId, device).
  - `GET /admin/flowmap/node-thumbnails/:nodeId` -> `{ phone?: string, tablet?: string, desktop?: string }` (per-device permanent-url map; 404 only when the node has none). Keep resolving the PERMANENT url via `resolve-permanent-url.ts`.
  - Update the service + specs accordingly.

### 2. Package: device-aware rendering (app-agnostic)

- Change the thumbnail resolver to be device-aware: `resolveThumbnailUrl?(nodeId: string, device: 'phone'|'tablet'|'desktop') => string | null | Promise<...>`. Card + device frame call it with the active device.
- Make the device selection drive the WHOLE board, not just one focused panel: lift the device choice to a board-level control (reuse the existing `flowmap_live_device` localStorage key) so picking phone/tablet/desktop re-renders every node's card screenshot at that device. The focused device frame shows the same device's screenshot.
- Focused-node behavior:
  - Default: show the per-device STATIC screenshot in the device frame (works for web + landing, no iframe, no CORS).
  - Same-origin web nodes: keep a "Go live" toggle that swaps the screenshot for the existing live iframe (do not remove that capability; just make it opt-in).
  - Landing nodes: keep the #208 "Open live" new-tab action.
- `onCaptureThumbnail` (live html-to-image capture) gains the device, so a live capture stores against the active device. Update its signature + the web wiring.
- Graceful fallback: when a device has no screenshot yet (resolver returns null), fall back to the label card (as today), do not show a broken image.
- Update/add co-located tests for the device-aware branch.

### 3. Capture: all three devices (apps/web)

- `capture-flowmap-shots.ts`: for each node, capture at ALL THREE real device viewports from `DEVICES` (`phone 390x844`, `tablet 834x1112`, `desktop 1440x900`), `deviceScaleFactor: 2` for crispness, `sharp` -> webp per device, and POST each to the endpoint with `?device=<d>&source=playwright`. Remove the single wrong-sized `VIEWPORT={1280,800}`. Keep the web (authed seed-admin) and landing (`--app=landing`, public, no login) modes; both now loop the three devices.
- Log per node+device how many shots uploaded / failed (no silent truncation).

### 4. Web host wiring (apps/web)

- `flow-client.tsx`: `resolveThumbnailUrl(nodeId, device)` -> GET the per-device map (cache the map per node, return the device entry); `onCaptureThumbnail(nodeId, blob, device)` -> POST `?device=`. Keep `resolveExternalUrl` (landing) as-is.

## Definition of done

- `pnpm --filter @lola/api test` passes (updated controller/service specs); `pnpm --filter @lola/api exec tsc --noEmit` clean.
- `pnpm --filter @lola/flowmap test` passes (device-aware tests); `pnpm --filter @lola/flowmap build` clean.
- `pnpm --filter @lola/web exec tsc --noEmit` clean.
- `pnpm --filter @lola/web flowmap:check` still green on all 4 boards (thumbnails live in Storage Brain, NOT in the committed maps, so the maps must not change beyond `generatedAt`).
- A migration for the `(nodeId, device)` key exists; `prisma generate` run.
- The device toggle drives per-device screenshots board-wide; landing nodes show a screenshot in the device frame (no iframe); web nodes still offer "Go live".
- Conventional-commit(s), subject lowercase after the colon, e.g. `feat(flowmap): per-device screenshots (phone/tablet/desktop) for every node incl. landing`.

## Constraints

- Stay in this worktree. Do not push. Operator handles push + PR + merge.
- Keep `@lola/flowmap` app-agnostic: device-aware resolver prop in, no lola URL / no Storage Brain client / no auth in the package.
- No URL or env value baked into any committed `flowmap.*.json`.
- No em-dashes or en-dashes anywhere. Use colons, parentheses, commas, periods.
- `/admin` is locale-free.
- Do NOT remove the existing same-origin live-iframe capability for web; make it opt-in behind "Go live".

## Notes: running the migration (avoids shared-DB drift)

This worktree shares the Docker postgres (`lola-stories-postgres-1`, port 5432). Use a dedicated per-worktree DB for `prisma migrate dev` ONLY:

```bash
docker exec lola-stories-postgres-1 psql -U lola -d lola_stories \
  -c "CREATE DATABASE lola_orch_flowmap_perdevice;"
DATABASE_URL='postgresql://lola:lola_dev@localhost:5432/lola_orch_flowmap_perdevice' \
  pnpm --filter @lola/api exec prisma migrate dev --name flowmap_thumbnail_per_device
```

(`lola_dev` is the committed local-dev password from `docker-compose.yml`.) Do NOT resolve any drift by copying another branch's migration. Optionally drop the DB when done.

## Notes: general

- `pnpm install` the worktree, then `pnpm --filter @lola/api exec prisma generate` and `pnpm --filter @lola/flowmap build` before web/api typecheck.
- Unit tests mock Prisma + the SDK; no live DB or running app needed for tests. Do NOT try to run the actual Playwright capture (it needs running apps + creds); adapt the script + leave running it to the operator.
- Commitlint: lowercase subject after the colon. The repo squash-merges; a Marlin-authored PR needs no bridge commit.
- If anything contradicts the codebase, prefer the codebase and record the deviation via `update_state` (`open_thread`). Do not stop and ask.
- When done, output a final message naming: the schema/migration change, the endpoint shape, the device-aware resolver prop, the 3-device capture, and confirmation the committed maps did not change.
