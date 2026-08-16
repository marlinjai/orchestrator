---
task: sp-erasure-consumer
spec: docs/plans/2026-08-16-multi-tenancy.md
depends_on: [sp-company-scoping]
shared_state: [env]
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Implement **slice S4** of `docs/plans/2026-08-16-multi-tenancy.md`: the GDPR
erasure consumer, so a company erasure in auth-brain actually deletes that
company's data here instead of completing while the data survives.

auth-brain fans a `tenant.erased` webhook out to every app that subscribes, and
an erasure is only COMPLETED once every subscribed app acks. social-planner is
registered as a suite app but deliberately does NOT subscribe yet, because
subscribing without a working consumer wedges every company erasure in
"awaiting app". This slice builds the consumer so the subscription can be turned
on.

## Read first

- `docs/plans/2026-08-16-multi-tenancy.md`, S4
- How slice S3 scoped data by `companyId` (read the merged code, do not assume)
- `src/lib/storage.ts`: how Storage Brain objects are written, so you can delete
  them by the same key convention
- The other suite consumers' contract, as described in auth-brain's
  `packages/app/src/lib/suite-apps.ts` comments for `agentic-os` and `storage`:
  signed, idempotent by event id, deletes rows AND stored objects, acks 2xx, and
  a company this app never served acks as a no-op rather than wedging.

## Definition of done

- `POST /api/internal/erasure`, **not** behind the normal session gate (it is a
  machine caller, not a browser). Add it to `publicPaths` in the auth config so
  the middleware lets it through, then authenticate it by SIGNATURE, never by
  session.
- **HMAC signature verification** using `SOCIAL_ERASURE_WEBHOOK_SECRET`, read
  from the environment (already provisioned in Infisical for prod). Compare in
  constant time. An unsigned, wrongly-signed, or replayed request is rejected and
  deletes nothing. Never log the secret or the raw signature.
- **Idempotent by event id**: keep an `ErasureEvent` table (event id primary key,
  received/processed timestamps). A repeat delivery of an already-processed event
  acks 2xx WITHOUT deleting again. This needs a Prisma migration.
- On a valid `tenant.erased` for company X, delete X's Projects, Posts, Media and
  SocialAccounts, **and the Storage Brain objects the media rows reference**.
  Deleting database rows while leaving the files is not erasure.
- A company this app never served acks 2xx as a no-op. Do not 404, do not error:
  that would wedge the erasure on auth-brain's side.
- Errors: a genuine failure (Storage Brain unreachable mid-delete) must return
  non-2xx so auth-brain retries, and must not mark the event processed. Partial
  success must be safe to retry, so order the work: delete objects first, then
  rows, and let a retry re-run the remainder.
- Tests: valid signature deletes exactly the target company's data and nothing
  else (seed two companies, assert the other is untouched); bad signature is
  rejected and deletes nothing; missing signature rejected; duplicate event id
  acks without a second delete; unknown company acks as a no-op; Storage Brain
  failure returns non-2xx and leaves the event unprocessed. Mock Storage Brain,
  no network in tests.
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit with a conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- **Do not touch the production database, Coolify, or Infisical.** The app is
  live at social.lumitra.co.
- Do not modify the auth-brain repo. Registering the subscription there is a
  separate, operator-run step AFTER this ships.
- Do not weaken or delete existing tests to get a green build.

## Notes

- `SOCIAL_ERASURE_WEBHOOK_SECRET` already holds one identical REAL value in both
  the auth-brain and social-planner Infisical projects (generated server-side
  2026-08-16, fingerprints verified equal). So the signature check has a real
  counterpart; you do not need to invent or scaffold the secret.
- Determine the exact signature scheme and header name from how auth-brain SIGNS
  the delivery. Do not guess a scheme: if the sending side's algorithm, header
  name or signed payload shape cannot be determined from what you can read,
  record the ambiguity with `update_state(kind="open_thread")` and implement the
  most standard reading (HMAC-SHA256 over the raw request body, hex-encoded)
  behind a single well-named function so it is a one-line change to correct.
- Erasure is legally load-bearing, not a nice-to-have. A silent partial delete
  that acks is worse than a loud failure that retries.
