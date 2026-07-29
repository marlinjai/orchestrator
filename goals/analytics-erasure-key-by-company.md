---
task: analytics-erasure-key-by-company
spec: orchestrator goals/HANDOVER-analytics-multi-company.md — gap found during S2 review (2026-07-29), blocks S4
depends_on: [analytics-projects-belong-to-companies]
verify: pnpm build && pnpm typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: key GDPR erasure off the COMPANY, not the workspace

**This is a compliance defect blocker found while reviewing S2. It is not in the
original handover.** S4 (deleting the two vestigial auth-brain workspaces) must
NOT run until this ships, or a GDPR erasure will silently fail to delete
analytics data.

## The defect

Analytics' erasure consumer deletes projects by workspace:

- `packages/dashboard/src/lib/erasure/handler.ts` calls
  `eraseWorkspaces(payload.workspace_ids ?? [], store)` for `tenant.erased`;
- `packages/dashboard/src/lib/erasure/erase.ts` resolves project ids via
  `store.findProjectIdsByWorkspaces(workspaceIds)`, i.e. `projects.workspace_id`.

auth-brain collects `workspace_ids` from the tenant's workspaces that still exist
at erasure time (`packages/app/src/lib/erasure/fanout.ts` — "collected BEFORE the
cascade deletes them"). So the moment S4 deletes the two per-project workspaces
(`lola-landing-6e00471d`, `lola-web-8f469eec`), a `tenant.erased` for Lola
Stories carries a `workspace_ids` list that no longer covers those projects,
`findProjectIdsByWorkspaces` returns `[]`, and the handler **acks a successful
no-op while the analytics data survives**. A silent, compliance-relevant failure.

S2 alone is safe (the workspaces still exist and `workspace_id` is still
populated). This slice closes the gap so S4 becomes safe.

## The fix

`tenant.erased` already carries `tenant_id`, and it is always set for a tenant
erasure (fanout spreads `...(input.tenantId ? { tenant_id: input.tenantId } : {})`
and `tenantId` is non-null on that path). Verify that yourself against the
published `ErasureWebhookPayload` rather than taking my word for it.

Post-S2, `projects.company_id` IS the auth-brain tenant id and is `NOT NULL`.
So deletion must resolve projects by **`company_id = payload.tenant_id`**. That
is strictly more correct than the workspace path: it covers every project of the
company regardless of workspace, and it does not depend on workspaces continuing
to exist.

- Replace the workspace-keyed resolution with a company-keyed one (a
  `findProjectIdsByCompany`-shaped store method, matching the existing store
  interface style).
- **A missing/empty `tenant_id` on `tenant.erased` must be a loud failure, not a
  silent no-op.** The current code treats an empty workspace list as "a verified
  no-op, never a delete-everything" — keep that defensive intent for the new key:
  never interpret an absent company as "delete everything", and never ack an
  erasure you could not actually perform. Failing the delivery so it retries and
  surfaces is correct; acking a no-op you cannot justify is not.
- Keep the existing idempotency/event-recording behaviour and the "complete only
  after ALL deletion work succeeded" ordering exactly as they are.
- `user.erased` is unaffected. Do not touch it.

`workspace_ids` stays in the published payload (other consumers may use it) —
this slice changes only what ANALYTICS keys off.

## Also update the stale contract comment in auth-brain

`packages/app/src/lib/suite-apps.ts` (auth-brain) describes analytics as
"WORKSPACE-scoped (not tenant-stamped)" and says it "deletes the rows keyed by
the payload's `workspace_ids`". After S2 that is wrong and actively misleading.

**Do NOT edit auth-brain in this slice** (different repo, and it is the live
identity service). Instead, state clearly in your final message that the comment
needs correcting, so the operator folds it into the next auth-brain PR.

## Tests (required)

- `tenant.erased` with a `tenant_id` deletes exactly that company's projects and
  their cascaded rows, and leaves another company's projects untouched.
- Projects are deleted **even when their `workspace_id` no longer corresponds to
  any live auth-brain workspace** — this is the S4 scenario and the whole point
  of the slice. Assert it explicitly.
- `tenant.erased` with a missing/empty `tenant_id` does NOT delete anything and
  does NOT ack as a completed no-op.
- Idempotent replay of a completed event is still a no-op.
- The existing wire-contract test that parses a REAL published
  `ErasureWebhookPayload` must still pass; extend it rather than weaken it.
- `user.erased` behaviour is unchanged.

## Definition of done

- The frontmatter verify chain exits 0. **Analytics CI BUILDS FIRST**
  (`build -> typecheck -> lint -> test`) — mirror that order.
- Final message confirms the auth-brain `suite-apps.ts` comment correction the
  operator must carry over.

## Constraints

- Do NOT touch auth-brain.
- Do NOT change the published erasure payload shape.
- Do NOT drop `projects.workspace_id` (a later follow-up does that).
- Do NOT weaken or delete existing tests to make the suite green.
