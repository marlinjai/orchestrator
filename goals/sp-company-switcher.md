---
task: sp-company-switcher
spec: docs/plans/2026-08-17-phase-3-scheduling-autopublish.md
depends_on: [sp-scheduler-publish]
shared_state: []
verify: pnpm test && pnpm typecheck && pnpm lint && pnpm build
verify_fix_cap: 2
---

# Goal

Phase 3, the remaining item in the plan's definition of done: **a user who belongs
to several granted companies can switch between them in the UI.**

Marlin joined both of Sharon's companies on 2026-08-17. Today the active workspace
comes from the session and there is no way to change it, so a multi-company user
lands in whichever company the session happens to hold and cannot reach the others.
Small, and blocking real use.

Build only this. No scheduler, no publisher, no Instagram work.

## Read first

- `src/lib/auth.ts` — `companyId(session)` is `session.activeWorkspace?.tenantId`,
  and `requireAuth` returns a session that exposes `memberships`
- `docs/plans/2026-08-16-multi-tenancy.md` — the tenancy rules
- `src/app/admin/**` — the shell the switcher lives in

## The mechanism (already researched, do not redesign it)

The active company is **not** a local cookie this app owns. It lives on the
auth-brain session. auth-brain exposes exactly the endpoint needed:

```
POST https://auth.lumitra.co/api/sessions/active-context
body: { "tenant_id": "<company id>" }     // workspace_id optional
```

Verified properties of that endpoint (read from auth-brain's source, not guessed):

- Authenticated by the `lumitra_session` cookie, so the browser must send it:
  `credentials: 'include'`.
- **Origin-allowlisted** to the suite domain: it accepts an Origin whose hostname
  equals `PUBLIC_SUITE_DOMAIN` or ends with `.<PUBLIC_SUITE_DOMAIN>`, so a call
  from `https://social.lumitra.co` passes. A missing Origin is treated as
  server-to-server. This is why the call is made **from the browser**, not from a
  server action proxying it.
- Authorization is enforced server-side on effective, inheritance-aware roles: a
  company the user may not activate returns 403, and an incoherent
  tenant/workspace pairing returns 400. **Do not re-implement those checks**, and
  do not treat a 403 as a bug: surface it.

So this app never decides what a user is allowed to activate. It offers the
companies the session already reports, asks auth-brain to switch, and re-renders.

## Definition of done

- The admin shell shows the **active company** and, when the session reports more
  than one membership, lets the user switch to another.
- With exactly one membership, the control does not pretend there is a choice:
  show the company name without a menu.
- Switching calls the endpoint above, and on success re-renders server data so the
  whole page (projects, media, posts) reflects the new company. A stale list from
  the previous company must never remain on screen: this is a tenant boundary, and
  a switch that half-applies looks exactly like a data leak.
- Failure paths are visible, never silent:
  - 403 -> "You no longer have access to that company", and the active company is
    unchanged.
  - 400 -> a clear message; do not retry blindly.
  - network/5xx -> a retryable error with the active company unchanged.
- No native `window.confirm` / `alert` / `prompt` anywhere; use the app's own UI.
- **The switcher changes nothing about server-side scoping.** Every route still
  derives `companyId` from the verified session, never from a request parameter,
  a body field, or anything the client can set. If you find yourself passing a
  company id from the client into a query, stop: that is the bug this whole
  tenancy model exists to prevent.
- Tests:
  - single membership renders no switcher
  - several memberships render each company, with the active one marked
  - a successful switch triggers the refresh path
  - 403 and 400 responses each surface their own message and leave the active
    company unchanged
  - the existing cross-company route tests still pass untouched
- `pnpm test && pnpm typecheck && pnpm lint && pnpm build` all pass.
- Single commit, conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not push to any remote.
- **Do not touch the auth-brain repo.** It is tier 3 (central identity service);
  changes there are Marlin's call. If something genuinely needs to change in
  auth-brain, write it as an open thread instead of doing it.
- Do not touch production, Coolify, Infisical, or the Meta app.
- Do not weaken or delete existing tests.
