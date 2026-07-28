---
task: studio-erasure-consumer
verify: pnpm db:generate && pnpm test && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Slice E3 of the GDPR erasure plan (governing doc lives in the AUTH-BRAIN repo; its app fan-out contract is restated here in full, treat THIS file as authoritative): Lumitra Studio consumes auth-brain's signed erasure webhooks, deletes the tenant's data AND stored assets, and acks idempotently. auth-brain (already deployed) is delivering `POST https://studio.lumitra.co/api/internal/erasure` with retries; until this slice deploys those retries 404 by design.

## Precondition (run FIRST, abort loudly on failure)

`npm view @marlinjai/auth-brain-shared@1.3.0 version` must print `1.3.0` (it carries the erasure webhook payload schemas). If not, STOP and report.

## The webhook contract (binding)

- `POST /api/internal/erasure`, JSON body `{ event_id, kind: "tenant.erased" | "user.erased", tenant_id?, user_id, requested_at }`; zod schemas exported by `@marlinjai/auth-brain-shared@1.3.0` (find the exact names in that package and use them; do not hand-roll a divergent shape).
- Signature: HMAC-SHA256 of the RAW request body with the shared secret env `STUDIO_ERASURE_WEBHOOK_SECRET` (already set in the studio Infisical project, prod), sent in a header (check the shared package/auth-brain fanout code contract exported alongside the schemas for the exact header name; mirror it exactly). Constant-time compare, min-length guard, fail-closed 401 on missing/bad signature or missing secret env (500 misconfigured, same discipline as previous gates). The route is exempt from the browser session middleware but NEVER from the signature check.
- Idempotency: a processed-events table (new Prisma model, e.g. `ErasureEvent` with `eventId @id`, kind, receivedAt, completedAt); a replayed `event_id` returns 200 no-op. Processing is transactional where possible; the ack (2xx) is sent only after ALL deletion work for the event succeeded; any partial failure returns 5xx so auth-brain retries (deletions must therefore be idempotent).

## Definition of done

1. **`tenant.erased` handling**: delete every row stamped with the tenant and everything hanging off those rows: `Brand` (+ BrandReference etc.), `Project`, `WorkflowRun` (+ node runs), `Character` (+ references), `Asset`, `Job`, chat `Session`/`Message` where they key to the tenant's brands/projects (follow the actual schema relations; nothing tenant-derived survives). ALSO delete the STORAGE assets those rows reference via the storage-brain SDK (the existing client patterns in the repo; batch + tolerate already-deleted). Then record the event and ack.
2. **`user.erased` handling**: Studio holds no user-keyed rows (everything is tenant-keyed), so: validate, record the event, ack 200. Add a comment stating this is a VERIFIED no-op by schema audit, not an omission.
3. **Middleware**: `/api/internal/erasure` exempted from session/bearer gates (signature is its auth); confirm no other `/api/internal/*` wildcard opens anything else.
4. **Tests**:
   - signature: valid passes; wrong secret / tampered body / missing header 401; missing env 500; timing-safe compare used
   - wire-contract: a REAL payload fixture built with the shared 1.3.0 schemas parses and processes; a signature computed the auth-brain way (same header, same algorithm) verifies: prove the two sides agree using the published package, not a local copy
   - idempotency/revision paths: replay of a completed event_id no-ops with 200; a FAILED partial run (storage delete throws) returns 5xx, leaves no event record marked complete, and a retry completes the remaining deletions
   - cascade: fixture tenant with brands/projects/runs/characters/assets: all rows gone, storage deletes called for each referenced asset (SDK mocked), OTHER tenants' rows untouched (isolation assertion)
   - `user.erased` records + acks without touching data
5. `pnpm db:generate && pnpm test && pnpm lint` green. Single conventional commit explaining the WHY.

## Constraints

- Stay in this worktree. Do not push.
- Do not change the tenant scoping, gates, or any existing route semantics; this slice ADDS one signed internal route + models + deletion logic only.
- Never log webhook bodies (they carry user ids), the secret, or signatures. Fail closed everywhere.
- No em-dashes or en-dashes anywhere. When done, output a final message that the task is complete.
