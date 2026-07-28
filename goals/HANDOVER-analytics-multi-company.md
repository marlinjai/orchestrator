---
type: handover
date: 2026-07-29
status: decided
summary: Analytics becomes a multi-company citizen. Marlin decided both open questions on 2026-07-29 - projects stop being workspaces, and the scope switcher is a hard boundary. Execute end to end.
tags: [analytics, auth-brain, multi-company, scope-switcher]
---

# HANDOVER: Analytics multi-company, DECIDED and ready to execute

You are the OPERATOR (Claude Code, `autonomous-orchestration` skill, agent teams).
Written 2026-07-29 by the session that shipped the B-sync authz wave.

**Marlin has authorised this whole chain to run end to end, unattended, including
the tier-3 auth-brain dispatches.** Cite this document when passing
`--confirm-stakes`. New tier-3 work OUTSIDE this chain still needs its own go.

**Do this first:** read the memory files `authz-decisions-prelaunch-gate.md` and
`reference_authz_bsync_live.md`, then PLAN the whole chain before writing code.
The slices below are dependency-ordered for a reason.

---

## THE TWO DECISIONS (both settled 2026-07-29, do not reopen)

### Decision 1: projects STOP being workspaces. YES.

Analytics currently mints one auth-brain **workspace per project** and uses
workspace membership as a per-project ACL. That was never a design choice, it was
a workaround: auth-brain's smallest scope is a workspace, so analytics used the
only vocabulary available.

It is the wrong layer, for four reasons that are all now accepted:

- It leaks an app's domain objects (a tracked website) into the identity service,
  which should only hold organisational containers people belong to.
- It does not scale: 50 tracked sites means 50 workspaces in the admin console
  and 50 entries in every user's verify payload on every request.
- It does not generalise. Studio does not do this per brand; receipts does not do
  it per client. Analytics is the outlier.
- It contradicts standing decision 3: role assignment is central, but what a role
  means INSIDE an app is that app's policy-as-code. Per-resource access is an
  inner rule that analytics pushed up into the platform.

**The target model:** a project belongs to a **company** (auth-brain `tenant`).
Access is company membership. A role matrix in analytics decides what
viewer/member/admin may do to a project, exactly like Studio's (lumitra-studio#125
is the reference implementation, `src/lib/auth/roleMatrix.ts`).

**Accepted cost:** per-project granularity is dropped. Anyone who can see a
company's analytics sees all of that company's projects. Nobody uses the
granularity today. If it is ever wanted, the correct home is FGA resource-level
sharing tuples inside auth-brain (already named as a future capability in
`docs/internal/fga-authoritative-tradeoffs.html`), NOT workspaces-as-ACLs.

### Decision 2: the scope switcher is a BOUNDARY, not a filter. 

The active company is an access edge, not a view preference:

- A project outside the active company returns 403/404 on EVERY entry point:
  page routes, API routes, direct URLs. Not merely hidden in a list.
- The active scope is re-validated against the user's LIVE roles on each request.
  A revoked role fails closed immediately, it does not wait for a new session.

Rationale: there are now genuinely separate companies with other people in them
(Opuntia is Sharon's, Return Hypnosis is a third party). Fail-closed is correct
the moment an access surface stops being "just Marlin".

---

## What is ALREADY TRUE (do not rebuild any of this)

1. **Analytics already has SSO.** `packages/dashboard/src/middleware.ts:17-18`
   redirects unauthenticated page navigations to `${AUTH_BRAIN_URL}/login`,
   exactly like Studio. Both ride the shared `lumitra_session` cookie. There is a
   `/request-access` page for the app-grant door.
2. **Analytics no longer talks to OpenFGA for sessions.** `openfga-direct.ts` was
   deleted (analytics-platform#38); project visibility already derives from the
   verify payload's `effective_roles`. ONE `can()` survives for CLI account keys
   (see "the account-key wrinkle" below).
3. **The tenant-level `viewer` role exists and is live** (auth-brain#73), lowest
   rung, read-only, `tenant.viewer = this OR member` (same-scope, no cross-tier
   cascade). Use it as the read tier.
4. **The switcher primitive is half-built.** `sessions.active_tenant_id` and
   `active_workspace_id` exist (migration 004), the verify payload returns
   `active_tenant`/`active_workspace`
   (`packages/shared/src/types.ts:153-154`), and
   `setActiveContext(sql, sessionId, tenantId, workspaceId)` exists at
   `packages/app/src/lib/db/repositories/sessions.ts:94` with **ZERO callers**.
   Only the endpoint is missing.
5. **The backfill is already done.** There are exactly TWO analytics projects,
   both Lola's, and their workspaces were moved to the Lola Stories company on
   2026-07-28. Nothing to reassign.

---

## The slices, dependency-ordered

### S1 (auth-brain): the active-scope endpoint + fail-closed read

Expose the switcher primitive. This is the highest-leverage slice because the
schema, the read path and the setter all exist and nothing calls them, and
because Studio and Receipts get the capability for free.

- A session-authenticated endpoint that sets the active scope, calling
  `setActiveContext`.
- **Never trust a client-supplied scope id.** Validate that the caller actually
  holds a role on the target tenant (and workspace, if given) before writing.
  Unauthorised target is a 403, not a silent no-op.
- **Close the latent read hole in the same slice:** `sessions/verify/route.ts:62`
  resolves `active_tenant` by id lookup WITHOUT re-checking that the user still
  holds a role there. So a revoked user keeps reporting their old active scope.
  Treat an active scope the user no longer holds as `null` on read (and clear it),
  fail-closed. This is what makes decision 2's "re-validated per request"
  guarantee real.
- **Default behaviour with no active scope set:** if the user has exactly one
  company, default to it; otherwise leave null and let the app require a pick. Do
  not silently pick the first of several.
- Revision-path tests per `knowledge-base/standards/stateful-flow-testing.md`:
  switch, switch back, switch to a scope you have lost access to (must fail
  closed), resume after re-login, and the no-active-scope default.
- Bump shared + SDK. Do NOT publish; the operator publishes.

### S2 (analytics): projects belong to companies

The heart of decision 1.

- Add `company_id` to `projects` (the auth-brain `tenant` uuid). Backfill BOTH
  existing rows to the Lola Stories company
  `019f6a89-ea4a-75d4-90ff-4e809491647e`:
  - `lola-landing`, domain `lolastories.com`, workspace `019ee142-44af-786d-9366-a705b7607f86`
  - `lola-web`, domain `app.lolastories.com`, workspace `019ee142-453c-702c-9e6e-cba872eadcca`
- **Delete `ensureAnalyticsTenant()` and `provisionProjectWorkspace()`**
  (`packages/dashboard/src/lib/workspace-provisioning.ts`) and the boot-time
  `provisionMissingWorkspaces()` step. Analytics must never write to auth-brain
  again: it CONSUMES companies, it does not create them. Remove the
  `AUTH_BRAIN_TENANT_SLUG` / `AUTH_BRAIN_TENANT_NAME` / `AUTH_BRAIN_GROUP_ID`
  env plumbing with it.
- Project CREATION takes a target company the caller actually holds a role on
  (validate against the verify payload; never trust the request body).
- Replace `hasWorkspaceAccess(effective_roles, p.workspace_id, ...)` in
  `packages/dashboard/src/app/api/projects/route.ts` with a company-role check.
- Add a Studio-style role matrix module as the single source of truth for
  action -> minimum company role. Copy the SHAPE of
  `lumitra-studio/src/lib/auth/roleMatrix.ts`, including its two good calls:
  `billing_admin` stays OFF the general ladder (it authorises billing only and
  never satisfies a viewer/member/admin check), and the `direct` vs `inherited`
  marker is IGNORED for gating (an inherited admin IS an admin).
- Leave `projects.workspace_id` in place but UNUSED in this slice; drop it in a
  separate follow-up migration once nothing reads it. Do not do both in one step.

### S3 (analytics): the switcher UI + boundary enforcement

- Read `active_tenant` from the verify payload; render the picker from the
  companies the payload already carries; call S1's endpoint to switch.
- Enforce decision 2 as a BOUNDARY on every project-scoped route and page, not
  just the list. A project outside the active company is 403/404.
- Handle the no-active-scope case per S1's rule.

### S4 (cleanup): retire the vestigial workspaces

Once S2 ships and nothing reads `workspace_id`, delete the two auto-created
workspaces (`lola-landing-6e00471d`, `lola-web-8f469eec`) from auth-brain via
`DELETE /api/admin/machine/workspaces`. Then run `openfga:reconcile` and confirm
zero findings. Do NOT use raw SQL.

### S5 (auth-brain, independent hygiene): a real platform_admins table

Can run any time; it touches migrations so do NOT run it in parallel with S1.

`seed-platform-admin.ts` writes `user:<id>#admin@platform:lumitra` straight to
FGA because "Phase 1 has no SQL `platform_admins` table". That shortcut forced a
permanent special-case in reconciliation (auth-brain#70 excludes the `platform`
type on both sides, or `--heal` would delete the tuple and lock the admin
console). Give platform admins a real table, seed through it, and then narrow or
remove the reconciliation exception so the safety of `--heal` no longer rests on
a hardcoded type exclusion.

---

## The account-key wrinkle (read before touching auth)

`checkAccountKeyProjectAccess` is the ONE surviving direct `can()` in analytics.
Account keys are developer CLI credentials (`ap_account_` prefix, minted through
the `cli_device_codes` device flow), NOT customer-facing ingest keys, and they
produce no verify payload at all, so there is nothing to read roles from.

Under S2 that path must become "does this user hold a role on the project's
COMPANY" instead of "on the project's workspace". It may still need a `can()`
against the `tenant` type, or a small auth-brain endpoint. Either is acceptable;
what is NOT acceptable is silently dropping the check or failing open. Keep it
fail-closed and keep the comment explaining why it exists.

---

## Traps. Do not relearn these.

- **Pushing code does not change authorization.** Adopting a new OpenFGA model is
  MANUAL: `openfga:push`, then set `OPENFGA_AUTHORIZATION_MODEL_ID` in Infisical
  (auth-brain project `97c4971e-78c1-4adf-83e1-6c0b5f13375c`, prod), then restart
  app AND worker. Between merge and that flip, production runs the OLD model.
  Record the previous model id as a rollback anchor before pushing.
- **Verify against the model the service actually queries**, never the repo's
  `schema.json`.
- **Raw SQL on identity data caused two incidents on 2026-07-28** (a company with
  no creation event; an untraceable key swap). Use the machine APIs at
  `/api/admin/machine/*`; they emit audit + outbox rows and keep tuples correct.
- **The reconcile CLI does not inherit the app's injected env through
  `docker exec`.** Read it from `/proc/<pid>/environ` of the node process and pass
  with `-e`. Command: `pnpm --filter @auth-brain/app openfga:reconcile`
  (report-only, exits non-zero when findings exist) and `-- --heal` to write.
  ALWAYS inspect the orphan list before healing: heal DELETES.
- **Inheritance cannot be tested against the in-memory FGA mock** (a mock cannot
  evaluate userset rewrites). Copy
  `packages/app/tests/integration/inheritance-openfga.spec.ts`, which spins up
  real OpenFGA.
- **Analytics CI builds first**; a stray non-route export in a Next route file has
  broken that build before. Studio's `pnpm test` is wrapped in `infisical run`.
- **Workers forget the lockfile on dependency bumps.** Analytics pins lag badly;
  the published versions are shared **1.6.0** and sdk **1.4.0**.
- `gh pr merge` from inside a worktree fails on local branch cleanup while the
  merge itself SUCCEEDS. Re-check `gh pr view --json state` before retrying.
- A PR can sit green and unmerged because it is a **draft** (that is exactly why
  the framer-clone CVE patch waited from Monday to Tuesday).

## Operating protocol (non-negotiable)

Per code slice: worktree off FRESH origin/main -> `orchestrator start` (background,
harness-tracked) -> review the diff against `git merge-base HEAD origin/main` ->
run the repo's FULL verify chain matching its CI exactly, gating on EXIT CODES,
never `test | grep` -> PR -> CI -> squash-merge -> watch the deploy -> **live-probe
the changed surface** -> clean up worktree and branches.

Post-deploy verification is not optional. Three defects in the last wave were
invisible to a green CI run and obvious within minutes of probing production.
After anything touching identity: re-run reconciliation and check the live model.

## Key ids

Orgs: `marlinjai` `019f6a90-8b69-7d7f-a8fe-268b62ae1cc7` (umbrella: Lumitra,
marlinjai, Whiz-Art Media), `Lola Stories` `019f6a89-ea38-7f0e-bbe7-544652b65f56`,
`sharondisalvo` (personal: Opuntia, Return Hypnosis).
Companies: `lumitra-core` `019ec2f2-f19e-70f4-a889-8afb34c314ca`, `lola-stories`
`019f6a89-ea4a-75d4-90ff-4e809491647e`.
Infisical: auth-brain `97c4971e-78c1-4adf-83e1-6c0b5f13375c`; analytics resolves
by workspace name "Analytics Platform".
Containers on shared-server-I (`157.90.119.98`): auth-brain app
`h10iicx7b1g7c5dj9z69z4f2*`, auth-brain worker `sedr9u7xa2y3fu8jkv3yjq04*`,
auth-brain DB `gzcpriw2sbpsuwka4spb788x`, analytics `u30x30hokl4flljrmvywy5t8*`,
analytics DB `j5hw5h60e1mujxgfvtaea87l`, storage DB `mexlrzpf5pa8u4g7bia65gd3`.
Current FGA model `01KYMAAS0X4W779CZ9G7S95BBA` (prior anchor
`01KYKZ8MG9HJVD9RNKKYG24N3H`).

## Also queued, NOT part of this chain

- **framer-clone PR #83 (CM-12)** fails `verify` for two distinct reasons:
  `COMMERCE_APP_DATABASE_URL` is not set in CI, and its own idempotency test hits
  `duplicate key value violates unique constraint "tenant_groups_slug_key"`. It
  is a month old and one commit behind main. Real work, not a rebase.
- Stale open PRs needing triage: lumitra-studio #75/#76/#77, analytics #32,
  lola-stories #264/#265 (#264 needs Marlin to listen to audio).
- **Marlin and Sharon still get forced TOTP enrollment** at their next
  auth.lumitra.co login, from the security hardening slice.
- The 361 orphaned `kie-input` storage files (371 MB) await Marlin's delete
  decision. Review page was built; evidence is conclusive; do NOT delete
  unilaterally.
