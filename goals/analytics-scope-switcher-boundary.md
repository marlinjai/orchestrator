---
task: analytics-scope-switcher-boundary
spec: orchestrator goals/HANDOVER-analytics-multi-company.md slice S3 (decision 2, settled 2026-07-29)
depends_on: [auth-brain-active-scope-endpoint, analytics-projects-belong-to-companies]
shared_state: [lockfile]
verify: pnpm build && pnpm typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: the company switcher, and the active company as a hard BOUNDARY

Marlin settled this on 2026-07-29:

> **The scope switcher is a BOUNDARY, not a filter.**

Concretely, and non-negotiably:

- A project outside the active company returns **403/404 on EVERY entry point**:
  page routes, API routes, direct URLs. Not merely hidden from a list.
- The active scope is **re-validated against the user's LIVE roles on each
  request**. A revoked role fails closed immediately; it does not wait for a new
  session.

Rationale: there are now genuinely separate companies with other people in them
(Opuntia is Sharon's, Return Hypnosis is a third party). Fail-closed is correct
the moment an access surface stops being "just Marlin".

This slice builds on two that already merged: auth-brain now exposes a validated
active-scope endpoint with a fail-closed verify read, and analytics projects now
carry `company_id` with a company role matrix. **Read both diffs before starting**
(`git log origin/main` in each repo).

## The cross-origin constraint — read before designing the switch call

Do NOT call auth-brain's active-scope endpoint from the browser. It cannot work:

- auth-brain serves **no CORS headers at all**;
- its CSRF cookie (`lumitra_csrf`) is **host-only to auth.lumitra.co**, so
  analytics.lumitra.co can never read it;
- the session cookie IS shared across `.lumitra.co`, so a server-side call can
  forward it.

**The switch must go through an analytics server-side proxy route**: browser ->
analytics' own same-origin API route -> (server-to-server, forwarding the
`lumitra_session` cookie) -> auth-brain `POST /api/sessions/active-context`.

Protect the analytics-side route with analytics' own conventions. Propagate
auth-brain's status faithfully: a rejected target must not surface as a success.

## The two enforcement seams (use them; do not sprinkle checks)

Analytics has exactly two places every protected surface funnels through. Put the
boundary in both, and nowhere else:

1. **Pages** — `packages/dashboard/src/app/(dashboard)/layout.tsx` calls
   `resolveSessionGate()` (`packages/dashboard/src/lib/auth.ts`). Note it
   currently **throws the verify payload away**, returning only a `CompatSession`
   of `{user}`. It must start carrying the active company and the user's
   companies, or every page will re-verify.
2. **API** — `authenticateRequest(request, projectId, requiredRoles)` and
   `authenticateAccountRequest(request)` in
   `packages/dashboard/src/lib/auth-api.ts`. Every project-scoped route already
   funnels through these (~30 routes under `/api/projects/[projectId]/**`,
   `/api/stats/**`, `/api/sessions/**`, `/api/heatmap/**`, `/api/test-links/**`,
   `/api/toolbar/**`).

A route must never assume the layout ran. Defense in depth: both gates apply.

## What to build

### 1. Carry the scope through the session gate

Extend `resolveSessionGate()` to expose what the switcher and the boundary need:
the active company (from the verify payload's `active_tenant`), and the list of
companies the user may switch to. Build that list from the payload analytics
already receives — do not add a second round trip, and do not invent a companies
API.

Only companies that actually carry the **analytics app grant** belong in the
picker. `evaluateAnalyticsGrant` already encodes the door; a company the user
holds but which has no analytics grant must not be offered as a destination.

### 2. The no-active-scope case

S1 defines the rule: exactly one company -> it is the default; more than one and
nothing chosen -> `null`, and the app must **require an explicit pick**. Read
what S1 actually shipped and follow it rather than re-deriving it.

`null` active scope must be a real destination, not a dead end or an empty app:
render a "choose a company" surface. A user with **zero** granted companies
already has a home (`/request-access`) — send them there, do not invent a second
empty state.

### 3. The boundary itself

- Every project-scoped surface resolves the project, then asserts the project's
  `company_id` **equals the active company**. Not "is one of the user's
  companies" — the ACTIVE one. That is what makes it a boundary rather than a
  filter.
- A project outside the active company is **404, not 403**. This is the
  established suite convention (auth-brain collapses unknown-and-foreign into 404
  in `lib/flows/tenant-api-keys.ts`; Studio does the same, documented in
  `src/lib/auth/scope.ts`: "a foreign resource is simply invisible (404), never a
  403 existence leak"). Do not leak which project ids exist in other companies.
- Re-validate the active scope against LIVE roles on each request. The verify
  payload is the live read (auth-brain re-checks and nulls a revoked scope as of
  S1), so honour `active_tenant: null` as "no scope" rather than falling back to a
  cached or client-supplied value. **Never** take the active company from a
  request header, query param, or body.
- Project LISTS filter to the active company too, so the list and the boundary
  can never disagree.

### 4. The picker UI

Render it in the dashboard shell (`packages/dashboard/src/components/layout/Sidebar.tsx`
and the `MobileNav` twin — both exist, keep them consistent). Match the existing
component and styling conventions; do not introduce a new UI library.

On switch: call the proxy, then make sure the app re-reads server state (the
active scope lives in the session, so stale client caches are a correctness
problem here, not a cosmetic one). Any project currently selected that does not
belong to the new company must be dropped, not silently carried across.

### 5. The account-key path

Account keys (`ap_account_`) carry no session and therefore no active scope. They
must keep authorizing by company membership on the project's own `company_id` (as
S2 left them), NOT by an active scope they cannot have. Do not accidentally break
machine callers by requiring an active company globally.

Public ingest (`/api/collect`, `/api/ingest`) authenticates by site key and must
**not** be gated by the company boundary. Do not touch it.

## Tests (required)

This is a stateful flow. `knowledge-base/standards/stateful-flow-testing.md`
applies and forward-only coverage is incomplete by definition. Cover:

- **Forward**: switch to company B, see B's projects, not A's.
- **The boundary, per surface class**: with A active, a direct request for a
  project in B returns 404 — assert this on a page route AND on an API route,
  including at least one `/api/projects/[projectId]/**` route and one
  `/api/stats/**` route. Not just the list endpoint.
- **Backtrack**: switch B -> A -> B; no stale project selection survives, and
  derived client state keyed to the old company is discarded.
- **Revocation mid-session**: the user loses their role on the active company;
  the very next request fails closed (no new session required).
- **Resume**: a reload / new session lands on the documented default, and a
  persisted client-side project selection whose company no longer matches is
  discarded rather than reattached.
- **No active scope**: with two companies and none chosen, protected surfaces do
  not silently pick one; the pick surface renders.
- **Zero granted companies** routes to `/request-access`.
- **Never trusts the client**: a request asserting a company via header/param/body
  is ignored.
- **Account key** still works without any active scope.
- **Public ingest** still works and is unaffected.

## Definition of done

- The frontmatter verify chain exits 0. **Analytics CI BUILDS FIRST**
  (`build -> typecheck -> lint -> test`) — mirror that order. A stray non-route
  export in a Next route file has broken this build before.
- If any dependency range changes, **COMMIT THE UPDATED LOCKFILE** (known
  recurring failure in this repo).
- Your final message lists every surface you gated, and names any project-scoped
  surface you deliberately left ungated with the reason.

## Constraints

- Do NOT touch auth-brain in this slice. If you find you need an auth-brain
  change, STOP and escalate.
- Do NOT re-open decision 1 or decision 2. Both are settled.
- Do NOT weaken or delete existing tests to make the suite green.
- Do NOT drop `projects.workspace_id` (a later follow-up does that).
- Do NOT delete the two vestigial auth-brain workspaces (a later operator step).
