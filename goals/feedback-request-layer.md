---
task: feedback-request-layer
spec: (none in-repo — implement from this goal + the referenced plan)
shared_state: [lockfile]
---

# Goal

Build the persistence-agnostic request layer of the Lumitra feedback-service (a Hono-on-Node app, Phase 1b seed). This is everything ABOVE the database: tenant resolution, rate limiting, payload validation, the delivery fan-out abstraction, and the `POST /v1/feedback` endpoint wired through a `FeedbackRepository` INTERFACE (no concrete DB implementation). The choice of data layer (Prisma vs postgres.js) is an open architecture decision and is OUT OF SCOPE for this task: leave persistence behind an interface with only an in-memory fake.

## Read first (read-only references, do NOT modify anything outside this worktree)

- This repo: `src/app.ts`, `src/env.ts`, `src/node.ts`, `src/middleware/error-handler.ts`, `src/routes/health.ts`, `README.md`, `package.json`, `tsconfig.json`, `eslint.config.mjs`. These establish the conventions you must match (Hono `createApp()` factory, ESM, `import type`, `@marlinjai/brain-core` error handler, `verbatimModuleSyntax`).
- Convention source (sibling Lumitra Hono API): `~/software-dev/ERP-suite/projects/lumitra-infra/storage-brain/packages/api/src/middleware/rate-limit.ts` — port its in-memory sliding-window `rateLimiter` + `tenantKeyFn`, but RETYPE the context off `any` to `Context<AppEnv>` (storage-brain uses `any`; do not copy that smell).
- Port-logic source (the same feedback flow already ported once): `~/software-dev/arbosano/src/app/api/feedback/route.ts` — the validation, throttle, and Trello/Google-Chat/Storage-Brain fan-out logic. Lift the SHAPE; this is a Hono service, not a Next route.
- Plan: `~/software-dev/knowledge-base/research/2026-05-27-feedback-service-lumitra.md` (Phase 1b section: `projects` table fields, `Feedback` fields, throttle 5/600s, destinations always-fire semantics).

If any cross-repo path is unreadable, proceed from the inlined spec below.

## Inlined spec (authoritative if a reference is unavailable)

- **Throttle**: 5 requests per 600 seconds per IP (Lola's setting). Tenant-keyed limiter exists too (key by API key when present, else IP).
- **Tenant resolution**: request carries `X-Lumitra-Project: <slug>` + `Authorization: Bearer <apiKey>`. Validate the key against a `ProjectStore` (hashed compare). On missing/invalid -> 401. On valid -> set tenant context (projectId, slug, destination config) for downstream handlers.
- **Feedback payload** (zod): `message` (string, 1..5000, required), `type` (enum: `bug` | `idea` | `praise` | `other`), optional context `{ url?, pathname?, userAgent?, buildSha? }`, optional `screenshots` (file uploads, max 5 total, each <= 5 MB). Support both JSON and multipart bodies; for multipart, parse files via Hono's `parseBody`/`formData`.
- **Destinations**: Trello + Google Chat ALWAYS fire (best-effort: a delivery failure logs but does NOT fail the request). Screenshots go to Storage Brain. Each destination degrades GRACEFULLY when its env creds are absent (skip + warn, never throw). Env var names: `TRELLO_API_KEY`, `TRELLO_API_TOKEN`, `TRELLO_LIST_ID`, `GOOGLE_CHAT_WEBHOOK_URL`, `STORAGE_BRAIN_API_KEY`, `STORAGE_BRAIN_WORKSPACE_ID`.

## Definition of done

Create, matching this repo's conventions:

1. `src/middleware/rate-limit.ts` — ported `rateLimiter({ windowMs, max, keyFn })` + `tenantKeyFn`, typed with `Context<AppEnv>` (NO `any`). In-memory `Map`, periodic cleanup. Add a code comment: "single-instance only; move to Postgres/Redis-backed if the service scales horizontally."
2. `src/feedback/project.ts` — `Project` type (id, slug, hashedApiKey, authMode: 'anonymous' | 'client-jwt', destinations config) + `ProjectStore` interface (`findBySlug(slug): Promise<Project | null>`) + an `InMemoryProjectStore` seeded from a constructor arg (for dev/tests).
3. `src/middleware/tenant.ts` — `tenantContext(store: ProjectStore)` Hono middleware. Reads the header + Bearer key, validates (constant-time-ish hashed compare is fine via a small helper), sets tenant vars on `c`, throws `ApiError` (from `@marlinjai/brain-core`, 401) on invalid. Extend `Variables` in `src/env.ts` with the tenant context fields.
4. `src/feedback/feedback.schema.ts` — zod schema(s) for the create payload + inferred TS types.
5. `src/feedback/delivery/types.ts` — `DeliveryService` interface (`name`, `deliver(feedback, project): Promise<void>`).
6. `src/feedback/delivery/trello.ts` + `src/feedback/delivery/google-chat.ts` — real `fetch`-based adapters that POST a card / webhook message, but SKIP with a warning when their env creds are absent (graceful). Keep payloads minimal and correct.
7. `src/feedback/delivery/storage-brain.ts` — a STUB adapter this slice: interface-conformant, logs "storage-brain delivery not yet wired" and skips. (Real SDK integration is a later slice; do not add the SDK dependency now.)
8. `src/feedback/feedback.repository.ts` — `FeedbackRepository` interface (`create(input): Promise<StoredFeedback>`, `get(id): Promise<StoredFeedback | null>`) + `InMemoryFeedbackRepository`. Comment clearly: "Persistence layer (Prisma vs postgres.js) is a pending decision; this in-memory impl is for dev/tests only."
9. `src/feedback/feedback.routes.ts` — `POST /v1/feedback`: tenant middleware, then rate limiter (5/600s), then zod validation, persist via the injected `FeedbackRepository`, then fire all injected `DeliveryService`s best-effort (Promise.allSettled; log failures). Return `201 { id }`. Validation failure -> 400 via ApiError. Throttle -> 429 (limiter handles it).
10. Extend `src/app.ts` `createApp(config)` to accept `{ projectStore, feedbackRepository, deliveryServices }` with sensible in-memory DEFAULTS so the app + tests run with zero external services. Mount `feedbackRoutes` at `/v1/feedback`. Keep `/health` working.

Testing (add `vitest` as a dev dep + `test` / `test:run` scripts):

- rate limiter returns 429 after `max` requests in the window.
- tenant middleware: 401 on missing/invalid key; passes + sets context on valid key.
- zod validation rejects empty message and bad `type`; accepts a valid payload.
- `POST /v1/feedback` returns 201 with the in-memory repo, and the stored row is retrievable.
- `POST /v1/feedback` returns 429 on the 6th rapid call from one IP.
- delivery services degrade gracefully: with no env creds set, the POST still returns 201 and no throw occurs.

Gates (all must pass):

- `pnpm lint`
- `pnpm typecheck`
- `pnpm test:run` (vitest, non-watch)
- Single conventional commit on the current branch, message describing the WHY (e.g. `feat(feedback): persistence-agnostic request layer (tenant, rate-limit, delivery, POST /v1/feedback)`).

## Constraints

- Stay in this worktree. Do not modify files outside it (cross-repo paths above are READ-ONLY references).
- **Do NOT push to any remote and do NOT open a PR.** Just commit on the current branch and output a final message. The operator handles review + push + PR + merge.
- **Do NOT choose a database layer.** No `prisma`, `@prisma/client`, `postgres`, `drizzle`, or any DB driver dependency. No schema, no migrations. Persistence stays an interface + in-memory fake. This is deliberate: the Prisma-vs-postgres.js decision is pending with the human.
- Match existing conventions exactly: ESM, `import type`, `verbatimModuleSyntax` (so type-only imports must use `import type`), no `any`, `@marlinjai/brain-core` `ApiError` for thrown errors, Hono `createApp` factory + `routes/` + `middleware/` layout.
- No em-dashes or en-dashes anywhere (project + global convention). Use colons, parentheses, commas, or new sentences. No emojis in code/comments.
- Do not add dependencies beyond `vitest` (+ its needed peers) and what is already present. If you believe another dep is strictly required, record it as an open thread instead of adding it.

## Notes

- The whole point of the interface boundaries is to let this land WITHOUT deciding the data layer. If you find yourself wanting to write SQL or a Prisma schema, stop: that is the next slice.
- Keep delivery best-effort: the user's feedback must be accepted (201 + persisted) even if every external destination is down or unconfigured. This is the "always fire, never block" property from the plan.
- After the commit, output a final message listing the files created and the test results.
