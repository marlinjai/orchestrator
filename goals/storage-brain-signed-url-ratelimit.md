---
task: storage-brain-signed-url-ratelimit
spec: docs/plans/2026-07-27-company-isolation.md (S3 hygiene follow-up)
verify: pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1200
---

# Goal: signed-url generation belongs in the gallery-load rate-limit bucket

## The bug (measured in production 2026-07-27)

Over a 6-hour window the live storage API served 846 × 200 and **54 × 429**:
about 6% of all requests were rate-limited. Every single 429 was on
`GET /api/v1/files/:fileId/signed-url`.

`packages/api/src/app.ts` already recognises this exact failure mode for byte
downloads and fixes it there:

```ts
const apiRateLimit = rateLimiter({ windowMs: 60_000, max: 100, keyFn: tenantKeyFn });
// Byte downloads arrive one-per-file when a gallery renders, so they get a
// dedicated, generous bucket instead of sharing the 100/60s API-operation budget
const downloadRateLimit = rateLimiter({ windowMs: 60_000, max: 1000, keyFn: tenantKeyFn });
...
app.use('/api/v1/files/:fileId/download', downloadRateLimit);   // generous bucket
app.get('/api/v1/files/:fileId/download', publicDownloadHandler);
// Remaining /files API operations (list, signed-url, permanent-url, delete)
app.use('/api/v1/files/*', apiRateLimit);                        // 100/60s
```

The reasoning applied to `/download` applies identically to `signed-url`: a
consumer that renders a gallery of N files asks for N signed URLs, one per file,
in one burst. The limiter is keyed per TENANT, so a whole product's user base
shares one 100/minute budget. lola-stories renders library pages of story covers
this way, which is what produced the 429s: user-visible broken images and audio.

## What to change

In `packages/api/src/app.ts`, meter the per-file URL-vending routes with
`downloadRateLimit` instead of the broad `apiRateLimit`, mounted BEFORE the
broad `/api/v1/files/*` limiter so the specific route matches first (exactly the
pattern the `/download` route already uses):

- `GET /api/v1/files/:fileId/signed-url`
- `GET /api/v1/files/:fileId/permanent-url` — same one-per-file-per-render shape;
  include it for the same reason. Verify the real route path in
  `packages/api/src/routes/files.ts` before wiring it, and only move routes that
  genuinely vend a URL for a single file.

Genuinely bulk/mutating operations (list files, delete, migrate) MUST stay on
the 100/60s `apiRateLimit`. Do not raise any existing limit value, do not make
the limiter global, and do not change `tenantKeyFn`.

Update the comment above the mount so it names the rule: routes that a gallery
render fans out one-per-file (download, signed-url, permanent-url) use the
generous bucket; API operations use the 100/60s bucket.

## Tests (required)

Extend the existing app/route tests so they prove the bucketing, not just the
happy path:

- more than 100 requests in one window to `signed-url` for one tenant keep
  succeeding (they are on the generous bucket) while the same volume of a
  genuine API operation (e.g. the files list route) still gets a 429;
- the existing `/download` bucketing behaviour is unchanged;
- rate-limit isolation between two different tenants still holds.

Do not delete or weaken existing tests to make the suite green.

## Definition of done

- The verify chain in this goal's frontmatter (mirroring CI: build, typecheck,
  lint, test) exits 0.
- No SDK or wire change, so no version bump.
- Commit message: `fix(api): meter per-file URL vending on the gallery bucket, not the API bucket`

## Constraints

- Touch only the rate-limit mounting in `app.ts`, its comment, and tests.
- Do NOT touch auth middleware, the erasure consumer, the webhook signature
  path, or tenant resolution.
