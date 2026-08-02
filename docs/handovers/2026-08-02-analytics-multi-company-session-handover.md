---
type: handover
date: 2026-08-02
summary: "Analytics multi-company chain executed end to end: 12 PRs across auth-brain, analytics, studio and orchestrator, all merged, deployed and verified live. Records the open ends, the traps, and a live finding that analytics has ingested zero events since 2026-07-28."
tags: [analytics, auth-brain, multi-company, scope-switcher, authz, handover]
projects: [analytics-platform, auth-brain, lumitra-studio, orchestrator]
---

# Session handover: analytics multi-company, executed

Source prompt: `goals/HANDOVER-analytics-multi-company.md`, now `status: archived`
and rewritten to lead with its own outcome. **Do not dispatch from that file
again.** It is kept for the decisions, not the instructions.

## The two decisions this implemented (settled by Marlin, not reopenable)

1. **Projects stop being workspaces.** An analytics project belongs to a
   **company** (auth-brain `tenant`). Access is company membership plus an in-app
   role matrix. Accepted cost: per-project granularity is gone. Anyone who can
   see a company's analytics sees all of its projects.
2. **The scope switcher is a BOUNDARY, not a filter.** A project outside the
   active company is invisible on every entry point (404, never 403, so foreign
   ids cannot be probed), and the active scope is re-read from the live verify
   payload on every request.

## Shipped: 12 PRs, all merged, deployed, verified live

| Repo | PRs |
|---|---|
| auth-brain | #76 active-scope boundary, #77 `platform_admins`, #78 seed idempotency, #79 SDK `invalidateSession`, #80 sdk 1.6.1 republish, #81 publish guard |
| analytics | #39 projects to companies, #40 erasure to company key, #41 switcher + boundary, #42 cache + stale copy, #43 deferred debts, #44 account-key retirement, #32 consent-free tier 1 |
| lumitra-studio | #76 dev ergonomics (`pnpm dev` self-starts Postgres) |
| orchestrator | #18 committed 70 untracked goal files + archived the source handover |

Mains at handover: auth-brain `415eb63`, analytics `6532b2c`, orchestrator
`3ed4836` (orchestrator has since moved on: another session is active there).

## Verified production state (2026-08-02)

- All four services 200: auth, analytics, studio, `api.storage-brain.lumitra.co`
  (note the storage host is `api.storage-brain...`, `storage.lumitra.co` does not
  resolve).
- Reconciliation `missing 0 / orphan 0 / suppressed 0 / open_findings 0`.
- analytics migrations applied through **021**. `projects.workspace_id` dropped
  (019), `account_api_keys` dropped (020), `daily_salts` created (021).
- 2 projects, both on the Lola Stories company `019f6a89-ea4a-75d4-90ff-4e809491647e`.
- `analytics` app grant on **Lola Stories only** (revoked from Lumitra).
- `platform_admins` seeded with 1 row (`marlinjaipohl@gmail.com`, `admin`).
- The two vestigial per-project workspaces are soft-deleted; the load-bearing
  `lola-stories` workspace is INTACT (never delete it, storage auth depends on it).
- **No OpenFGA call anywhere in analytics.** Decision 2's one-decision-plane rule
  is now literally true rather than "true except one survivor".

## LIVE FINDING, unresolved: analytics has ingested nothing since 2026-07-28

```
2026-07-23    3 events
2026-07-24   63
2026-07-27  953   (5 visitors)
2026-07-28    2
(nothing since)
```

The last event predates the 2026-07-31 deploy by three days, so this is NOT
caused by any of the above. `daily_salts` is consequently empty (salts mint
lazily on first ingestion of the day).

The tracker bundle serves 200 and both Lola sites load 200, but **neither
server-renders any reference to `analytics.lumitra.co`**. curl cannot distinguish
"absent" from "injected client-side after hydration", so this is a strong hint,
not a proof. **Check in DevTools.** If the tracker is not installed, analytics has
been collecting nothing for some time.

Side effect: the visitor-key cutover artifact that #32 warns about is MOOT for
history, because there were no visitors on the cutover day to double-count.

## Three claims in the source handover that were FALSE

Each cost real planning time. Recorded so the next handover author is careful.

1. **"The switcher endpoint is missing, `setActiveContext` has zero callers."**
   It shipped in PR #3. It was also quietly wrong: it validated DIRECT membership
   rows only, so once inheritance landed (#69) an org owner with inherited rights
   got a **false 403** on a company they controlled.
2. **"Copy `lumitra-studio/src/lib/auth/roleMatrix.ts`."** That file does not
   exist. The real pattern is `permissions.ts` + `can.ts` + `scope.ts`, and Studio
   returns 404 for a foreign resource to avoid existence leaks.
3. **Unstated but decisive:** auth-brain serves **no CORS** and its CSRF cookie is
   **host-only**. Analytics can therefore never call the switch endpoint from the
   browser. S3 had to proxy server-to-server, and S1 had to NOT gain a body CSRF
   token (it would have been unobtainable by the only caller it exists to serve).

## Two problems the source handover did not know about

**S4 would have silently broken GDPR erasure.** Analytics deleted projects via
`payload.workspace_ids`, and auth-brain builds that list from workspaces that
still exist at erasure time. Deleting the vestigial workspaces would have made a
`tenant.erased` match zero projects and **ack success while the data survived**.
Fixed in analytics#40, which had to land BEFORE S4 ran.

**A grant/data divergence made the switcher useless.** The `analytics` entitlement
sat on the Lumitra company while the projects belonged to Lola Stories, so once
the boundary made the specific company matter, the only offered company owned zero
projects. Fixed by granting analytics to Lola Stories and revoking from Lumitra.

## Open ends

### Needs Marlin's judgment
- **studio #75** (R3F 3D render adapter, +1088/-4): is the 3D workstream live, and
  is "pure 3D now, FX bridge later" still the sequencing?
- **studio #77** (video in the chat surface): product plus cost. Video is the
  expensive modality and this puts it one sentence away rather than behind a
  deliberate canvas action.
- **framer-clone #83**: is commerce still active? Two known failures:
  `COMMERCE_APP_DATABASE_URL` unset in CI, and a real `tenant_groups_slug_key`
  unique violation in its own idempotency test. If dormant, close it.
- **lola-stories #264 -> #265** (both drafts, ORDERED): #264 exists so Marlin can
  **listen** to a German multi-voice story and judge ElevenLabs v3. #265 is 2864
  lines of engine built on that verdict. One listening session unblocks both.
- **361 orphaned `kie-input` files, 371 MB** on Lola's storage tenant
  (`af895591-0b40-4fb0-8f33-040428eab48d`), created 2026-06-01 to 06-04, nothing
  since. Second-largest context there, ~29% of the tenant. Irreversible, so NOT
  deleted. Query to re-inspect is in the session transcript.
- **Lawyer review** (pre-launch gate item 8), the only non-engineering item left.

### Operational
- **Mint a replacement CLI credential.** The local account key died with #44's
  hard cutover. Mint a COMPANY-scoped auth-brain service-account key for Lola
  Stories and set `LUMITRA_ACCOUNT_KEY`. Do NOT let an agent mint it: the
  plaintext is returned once and must never enter a transcript.
- **Investigate the zero-ingestion finding above.**

### Known limitations, documented not fixed
- The 30s verify cache means analytics honours a **revoked role for up to 30s**,
  which qualifies decision 2's "fails closed immediately". Accepted trade with the
  reasoning in `packages/dashboard/src/lib/auth-brain.ts` (each uncached verify
  costs auth-brain ~11 OpenFGA round trips).
- The SDK verify cache is **per-process**. Fine on one container; it becomes a
  real bug the day analytics scales to multiple replicas.
- `sessionize.integration.test.ts` needs `RUN_CH_IT=1` + a live ClickHouse and
  never runs in CI. It was run manually against ClickHouse 24.10.2.80 before
  merging #32 (4/4 pass, including the `gap >= 1800s` boundary case).
- Adding `userAgent` to the visitor key permanently changes what "a visitor"
  means (same person, two browsers, now two visitors). Expect a step change in
  visitor levels whenever traffic resumes. Pageviews and sessions are unaffected.

## Traps, do not relearn these

- **Never `npm publish` a package declaring a `workspace:` dependency.** pnpm
  rewrites the protocol at pack time; npm does not and does not warn. This shipped
  a broken `@marlinjai/auth-brain-sdk@1.6.0` to the public registry. Guarded since
  auth-brain#81 (`prepublishOnly` + `pnpm check:packed-manifests`), but the trap
  generalises to any pnpm workspace that publishes.
- **Suspect the mocks.** FIVE defects this session came from a mock being more
  permissive than the real service: the FGA duplicate-write mock, the erasure
  fixtures keeping workspaces alive, the SDK cache living inside the real client
  so a mocked client never went stale, the packed manifest, and route tests
  stubbing a boolean instead of exercising the role ladder. When you fix a bug of
  this class, fix the mock too or it returns.
- **The reconcile CLI on prod**: `docker exec` does not inherit injected env. Read
  it from `/proc/<pid>/environ`, and pick the process whose environ actually
  contains `DATABASE_URL=`, NOT simply the first `node` process. Resolve, run and
  redact entirely on the remote host so no secret enters a transcript.
- **`gh pr merge` from a worktree fails on local branch cleanup while the MERGE
  SUCCEEDS.** Always re-check `gh pr view --json state` before retrying.
- **Verify against the model the service actually queries**, never the repo's
  `schema.json`. Adopting an FGA model is a MANUAL post-merge step.
- **A green deploy proves nothing.** Migrations run behind a boot hook that never
  blocks startup, so a failed migration is silent. Check the table state.

## Related memory

`analytics-multi-company-shipped`, `reference-publish-and-mock-traps`,
`authz-decisions-prelaunch-gate`, `reference_authz_bsync_live`.
