---
task: analytics-authz-consolidation
spec: auth-brain docs/plans/2026-07-24-authz-hardening.md decision 2 + docs/internal/authorization-overview.html section 06
depends_on: [auth-brain-bsync-inheritance-v2]
verify: pnpm build && pnpm typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: analytics authorization consolidated onto the verify payload (gate item 9)

analytics-platform currently makes its own direct OpenFGA `can()` calls for
per-project authorization. Decision 2 says there is ONE decision plane: apps read
the verify payload and nothing else. OpenFGA stays auth-brain's internal engine,
plus the platform-admin gate and future sharing graphs. No app talks to FGA
directly.

By the time this slice runs, the verify payload delivers EFFECTIVE roles
(inheritance evaluated in the FGA model inside auth-brain) with a
direct-vs-inherited marker, which is what makes this consolidation possible
without losing semantics.

## What to change

1. **Inventory first.** Find every direct OpenFGA usage in analytics: the client
   wrapper, every `can()`/`check()`/`ListObjects` call site, and for each one
   record WHAT it decides (which resource, which relation, which user). Put this
   inventory in your final message before/alongside the diff. Do not guess.
2. **Map each check onto the verify payload.** For each call site, replace the
   FGA round-trip with a decision derived from the payload's memberships and
   effective roles. Where a check has no payload equivalent, STOP and escalate
   rather than inventing a local rule: a silent semantic change here is an
   access-control bug.
3. **Delete the direct FGA dependency** from analytics once no call sites remain
   (client wrapper, config/env vars, package dependency). If any FGA usage must
   survive, name it explicitly and justify it against decision 2.
4. **Preserve fail-closed behaviour.** An auth-brain outage, an unknown key, a
   missing grant, or an absent role must DENY. Never fall back to "allow because
   we could not check".

## Semantics that must not drift

- A user's access to a project must be at least as strict after this change as
  before. If a mapping would WIDEN access, stop and escalate.
- Inherited roles count exactly like direct roles of the same level (that is the
  point of computing effective roles centrally); the direct-vs-inherited marker
  is for display and revocation semantics, not for gating.
- A plain company `member` does NOT get workspace access without a direct
  workspace membership (the B slice removes that cascade).

## Tests (required)

- Per replaced call site: an allowed case and a denied case, asserted against the
  payload shape rather than a mocked FGA response.
- Fail-closed on verify failure/timeout.
- Inherited-role acceptance parity with direct roles.
- At least one test that exercises the REAL published verify schema rather than a
  hand-written mock. Mock-only coverage is exactly how the workspace-grant 403
  shipped: storage-brain mocked a payload real auth-brain never sent.

## Definition of done

- Verify chain exits 0. Note: analytics CI BUILDS FIRST — mirror its exact order,
  and be aware a stray non-route export in a Next route file has broken this
  build before.
- The call-site inventory and the old-check -> new-check mapping are in your final
  message.
- No direct OpenFGA calls remain in analytics (or the survivors are named and
  justified).

## Constraints

- Do NOT change auth-brain in this slice.
- Do NOT change what analytics MEANS by a project or its access rules; this is a
  consolidation of WHERE the decision comes from, not a redesign of policy.
