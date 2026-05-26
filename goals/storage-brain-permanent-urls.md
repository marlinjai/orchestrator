---
task: storage-brain-permanent-urls
spec: (none — design + implement from this goal)
---

# Goal

Add **permanent, non-expiring file URLs** to storage-brain so downstream consumers
(currently: lola-stories Trello feedback attachments) can attach a stable link
to a file that survives indefinitely. The mechanism MUST be revocable by
rotating a server-side secret so a leaked link can be killed without
re-uploading the file.

Background: lola-stories currently attaches `screenshot.url` (from the SDK upload
response) to Trello cards. That URL is broken in production (`http://api/v1/files/<id>`,
internal Docker hostname leaking) AND has no public-resolvable form. R2-style
presigned URLs cap at 7 days, which is too short for review-backlog cards.

Solution shape (HMAC permanent tokens): build on the existing
`public-download.ts` + `verifySignedToken` + `URL_SIGNING_SECRET` infrastructure
already in this repo. Extend the signed-token validation to accept a "no
expiry" mode (e.g. `expires=0` or a separate `permanent` token shape), and add
an SDK method `getPermanentUrl(fileId)` that returns this URL.

## Read first

- `packages/api/src/routes/public-download.ts` (existing signed-token path)
- `packages/api/src/services/signed-url.ts` (token gen + verify)
- `packages/api/src/routes/files.ts` (look at the existing `/signed-url` route at the bottom of the file — that's the model for the new endpoint)
- `packages/sdk/src/client.ts` (where `getSignedUrl` lives — add a sibling)
- `packages/sdk/src/types.ts` (response types)
- `CLAUDE.md` and `README.md` for repo conventions
- The existing `*.spec.ts` files for files.ts / public-download.ts / signed-url.ts service to learn the test idioms
- `CHANGELOG.md` and `packages/sdk/package.json` for version conventions

## Definition of done

API:
- New endpoint `GET /api/v1/files/:fileId/permanent-url` (auth: Bearer, tenant-scoped). Returns `{ url, fileId }` where `url` is fully qualified (uses the public base, NOT the internal docker hostname). Token uses HMAC with `URL_SIGNING_SECRET` over `(fileId, tenantId, "permanent")` with NO expiry component.
- `public-download.ts` accepts the new permanent-token mode: if `expires` param is absent OR `0`, treat as a permanent token and validate without expiry check. Tenant-id (`tid`) still required.
- Backward compat: existing signed URLs with `expires=<timestamp>` continue to work exactly as today.

SDK (`@marlinjai/storage-brain-sdk`):
- New method `getPermanentUrl(fileId: string): Promise<{ url: string; fileId: string }>` on `StorageBrain` client.
- Type added to `types.ts`.
- Minor version bump (e.g. 0.7.1 → 0.8.0). Update CHANGELOG.

Tests:
- Unit tests for the new endpoint (success, missing tenant, wrong token, file-not-found, cross-tenant access denied).
- Unit test for `public-download.ts` permanent-token branch.
- SDK client test for `getPermanentUrl` (mock fetch).
- `pnpm test` passes (all packages).
- `pnpm typecheck` passes.
- `pnpm lint` passes.

Repo housekeeping:
- CHANGELOG entry under "Unreleased" or appropriate version header (follow existing style).
- README update if user-facing API surface is documented there.
- Single conventional-commit on the branch describing the WHY ("feat(api,sdk): permanent HMAC URLs for revocable long-lived file links").
- Open a PR against `main` titled "feat: permanent file URLs (revocable via secret rotation)" with a Test Plan section.

## Constraints

- Stay in this worktree.
- Do NOT push directly to main. Push the feature branch and open a PR via `gh pr create`.
- Do NOT change the existing signed-URL behavior — only ADD the permanent variant.
- The `URL_SIGNING_SECRET` env var already exists; do not introduce a new secret. Rotation = rotate that secret.
- The returned URL must use the public base. If a `PUBLIC_BASE_URL` env var doesn't exist, add it (with a sensible default for local dev) and document it in README + Dockerfile env var list.
- Do NOT modify lola-stories or any other consumer in this run. The consumer migration is a separate task that depends on this one shipping + SDK publish.

## Notes

- The token derivation should be deterministic given (fileId, tenantId, secret). Same inputs → same token. This is how rotation works: change secret → all tokens invalid.
- Use base64url (no padding) for the token in the URL (matches existing signed-url convention if it does; otherwise hex is fine — be consistent).
- The endpoint result `url` is the fully-formed URL that consumers can paste into Trello/email/wherever. Include all query params (`?token=...&tid=...&expires=0` or whatever scheme you settle on).
- If you discover the existing `getFile()` `url` field is broken (returns internal hostname), DO NOT also fix that here — leave a comment / open_thread / TODO noting it and stay scoped to permanent URLs only. Scope discipline matters.
- After commit and PR open, output a final message confirming: branch name, PR URL, and SDK version bumped to.
