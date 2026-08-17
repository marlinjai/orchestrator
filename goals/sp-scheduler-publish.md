---
task: sp-scheduler-publish
spec: docs/plans/2026-08-17-phase-3-scheduling-autopublish.md
shared_state: [lockfile, prisma, migrations, env]
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Phase 3 slice 2: **the system publishes a scheduled post to Instagram by itself.**
A tick runs on a schedule, finds posts that are due, and pushes them through the
Meta Graph API. No human action, no nudge email.

Slice 1 (`sp-instagram-connect`) already landed the connect flow and the
encrypted long-lived token. This slice consumes that token; it does not change
how it is obtained.

Do NOT build the company switcher here (separate goal, `sp-company-switcher`).

## Read first

- `docs/plans/2026-08-17-phase-3-scheduling-autopublish.md` — the whole plan
- `docs/plans/2026-08-16-multi-tenancy.md` — the tenancy rules every route follows
- `src/app/api/internal/erasure/route.ts` — the existing machine-caller pattern:
  shared-secret auth, in `publicPaths`, idempotent by event id. The tick route is
  the same shape of thing; copy its discipline rather than inventing a new one.
- `src/lib/storage.ts` — `getPublicUrl(fileId, expiresIn)` is what gives Meta a
  URL it can fetch
- `src/lib/auth.ts` — how `companyId` is derived from the verified session
- whatever slice 1 added for token decryption and `needs_reconnect`

## What is already true (verified 2026-08-17, do not re-verify by guessing)

- **The signed URL works for an anonymous fetcher.** Storage Brain's
  `GET /api/v1/files/:id/download?token=…&expires=…&tid=…` needs **no**
  Authorization header. Measured against the live API: HTTP 200, full bytes,
  correct `Content-Type`, `Access-Control-Allow-Origin: *`. So
  `getPublicUrl(media.storageKey, …)` is a valid `image_url` / `video_url`.
- **Meta app is ready.** App id `1438203984819060`, Instagram app id
  `1888474835839729`, development mode, `instagram_business_content_publish`
  ready for testing, testers accepted. The redirect URI
  `https://social.lumitra.co/api/instagram/callback` **is registered**.
  `INSTAGRAM_APP_SECRET` holds a real value.
- **`SOCIAL_CRON_SECRET` is provisioned** in Infisical (social-planner, `prod`
  and `dev`, path `/`). Use exactly that name. Do not invent another, and do not
  try to write secrets yourself.

## Two hazards this slice must handle, not discover in production

1. **Instagram only ingests JPEG for feed images.** This app accepts PNG, GIF and
   WebP uploads, so the original object is often not a JPEG and Meta will reject
   it. The publish path must hand Meta a JPEG: derive a JPEG rendition at publish
   time (sharp, as the thumbnail path already does), upload it to Storage Brain,
   and pass that signed URL. Never publish a non-JPEG original and hope.
2. **Storage Brain ignores `Range` requests while advertising `Accept-Ranges:
   bytes`.** A ranged GET returns 200 with the whole body and no `Content-Range`
   (measured). Meta's video fetcher commonly uses ranged reads, so Reels
   ingestion may fail for a reason that has nothing to do with this app. Do not
   attempt to fix Storage Brain here. Instead: when a Reel container never
   reaches `FINISHED`, or comes back `ERROR`, record the container's
   `status_code` and any error field verbatim on the post so the cause is
   visible, and surface it. A silent "it just didn't publish" is the failure mode
   to avoid.

## Design

### The tick

- **A Coolify scheduled task hitting an authenticated route**, never an
  in-process timer. This container restarts often and a timer dies with it,
  silently. Route: `POST /api/cron/publish-tick`.
- Auth: `SOCIAL_CRON_SECRET` as a bearer token, compared with a **timing-safe**
  comparison, never `===`. The route goes in `publicPaths` exactly like the
  erasure endpoint, because the caller is a machine with no session.
- A missing or wrong secret is 401 and publishes nothing.
- The route is **not** company-scoped by session: it sweeps every company. That
  makes correct per-project scoping load-bearing. Resolve each post's project and
  account through the post's own relations; never widen a query to "all accounts"
  and match up later.
- Selection: posts with `status='scheduled'` and `scheduledAt <= now()`, oldest
  first. Bound the batch size per tick so one backlog cannot run forever.
- The tick is **re-entrant safe**: two overlapping ticks must not publish the
  same post twice (see idempotency below).

### The publisher seam

```ts
interface Publisher {
  publish(post: PostWithMedia): Promise<PublishResult>;
}
```

Chosen per project from `SocialAccount.status`:

- `auto` **and** a valid non-expired token -> `InstagramGraphPublisher`
- anything else (`assisted`, expired token, `needs_reconnect`, no account) ->
  `AssistedPublisher`, and the UI must say *why* it fell back.

Selection is a pure function of stored state and must be unit-tested directly.

**`AssistedPublisher` does not exist yet.** The plan calls it "the current
behaviour", but there is no publisher, no queue and no email code anywhere in
`src/`. Do not go looking for it. Build the minimum honest version: it publishes
nothing, moves the post to a distinct `needs_attention` state carrying a
machine-readable reason (`no_account`, `token_expired`, `not_business_account`),
and notifies (below). It must never leave a due post sitting silently in
`scheduled` forever, because that looks identical to "the scheduler is broken".

### The publish call

Three steps, per Meta's content-publishing flow:

1. `POST /{ig-user-id}/media` with a public `image_url` (feed) or `video_url`
   plus `media_type=REELS` (reel), and the caption. Returns a **creation id**.
2. Poll `GET /{creation-id}?fields=status_code` until `FINISHED`. Images are
   usually immediate; video never is. Publishing before `FINISHED` fails.
   Bounded polling with a sane interval and a hard timeout; `ERROR` or
   `EXPIRED` ends the attempt with the reason recorded.
3. `POST /{ig-user-id}/media_publish` with the creation id. Returns the
   **published media id**.

### Quota

Call `GET /{ig-user-id}/content_publishing_limit` **before each publish**. The
limit is 100 posts per rolling 24h. At quota, stop for that account cleanly and
leave the post `scheduled` for a later tick. Never learn the limit by being
rejected, and never burn the retry budget on quota.

### Missed windows

- Due within the last **60 minutes**: publish. Slightly late is fine.
- Older than that: do **not** publish. Set `missed`, notify, let a human decide.
- **Never silently roll to another day.** Moving someone's content to a different
  time is an editorial decision the system does not get to make.

### Notification

There is no email code in this repo yet and no user email stored: auth-brain
holds identities, this app does not. So keep notification small and truthful:

- The durable channel is the **database state plus the UI**: `missed`, `failed`
  and `needs_attention` posts are visible on the project with their reason and
  last error. This is what must always work, and it is what the tests cover.
- On top of that, send an email through Resend (`RESEND_API_KEY` is already in
  the environment) to `SOCIAL_NOTIFY_EMAIL` when that variable is set. When it is
  unset, log one clear line and carry on. Never let a failed notification fail a
  publish, and never let it crash the tick.
- Do not invent per-user email plumbing or call auth-brain for addresses.

### Idempotency: a post must never publish twice

`media_publish` is not idempotent, so the database is the guard:

- Persist the creation id **before** calling `media_publish`, and the published
  media id **immediately after** it returns.
- A post that already carries a published media id is never published again, by
  any path, including a manual retry.
- Claim the post before working on it (status transition to a `publishing` state
  under a conditional update, so a second concurrent tick's claim fails). A retry
  that finds a persisted creation id resumes at the poll/publish step rather than
  creating a second container.

### Failure handling

- Bounded retries with backoff, then `failed`, always surfaced, never silently
  dropped.
- Record `attemptCount`, `lastAttemptAt` and `lastError` on every attempt.
- **Token expiry is its own state**, not a generic failure: it means "reconnect
  this account" and the UI must say exactly that.
- Never log a token, a signed URL query string, or an app secret. Not in errors
  either.

### Schema

Extend `Post` with what the above requires (creation id, published media id,
attempt count, last attempt, last error) and widen `status` to include the
publishing/missed/failed states. Migration must be additive and safe on a
non-empty table.

## Definition of done

- A post scheduled a minute or two out is **published to Instagram by the tick**,
  with no human action, and `publishedAt` plus the published media id recorded.
- Reels publish through the same path with `media_type=REELS` and real container
  polling.
- The publish-limit check runs before each publish and stops cleanly at quota.
- Inside the grace window a late post publishes; outside it the post is `missed`
  and notified, and never published.
- A failure retries with backoff and then surfaces; a post is never published
  twice, including under two overlapping ticks.
- An account not eligible for auto-publish falls back to assisted and the UI says
  why.
- Non-JPEG originals publish correctly via a derived JPEG rendition.
- Tests, Graph API fully mocked, no network:
  - the three-step publish including a `status_code` that is not `FINISHED` on
    the first poll and `FINISHED` on a later one
  - quota exhaustion stops publishing and leaves the post schedulable
  - grace-period boundary on **both** sides (59 min publishes, 61 min misses)
  - retry-then-surface, with attempt count and last error persisted
  - double-publish prevention: a post with a published media id is skipped, and
    two concurrent ticks publish exactly once
  - resume: a post that already has a creation id does not create a second
    container
  - publisher selection from `SocialAccount.status`, including expired token ->
    assisted, with the reason recorded on the post
  - a failing or unconfigured notifier does not fail the publish or the tick
  - cron route: no secret -> 401, wrong secret -> 401, right secret -> runs
  - cross-company scoping for every new user-facing route, exactly as the
    existing routes do
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit, conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not push to any remote.
- **Do not touch the production database, Coolify, Infisical, or the Meta app.**
  The Coolify scheduled task is registered by the operator after merge; describe
  the exact schedule and URL in the PR description instead of configuring it.
- Do not build the company switcher, stories, carousels, or analytics.
- Do not weaken or delete existing tests.
- Never log or return an access token, in any code path, including errors.

## Notes

- `SOCIAL_PLANNER_STORAGE_BRAIN_API_KEY` in prod is currently a wrong value and
  uploads 401 against Storage Brain. That is an operator fix, not yours. It does
  not block this slice: build and test against mocks.
- The tick's schedule (every 5 minutes is the obvious default) interacts with the
  60 minute grace window: a post is only ever "missed" if the app was down for
  more than the window, which is what the state is meant to capture.
