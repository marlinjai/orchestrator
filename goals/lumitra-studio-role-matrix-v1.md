---
task: lumitra-studio-role-matrix-v1
spec: auth-brain docs/internal/authorization-overview.html section 05 + docs/plans/2026-07-24-authz-hardening.md decision 3
depends_on: [auth-brain-bsync-inheritance-v2]
verify: pnpm lint && pnpm build
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal: Studio inner-rule role matrix v1 (pre-launch gate item 5)

Studio currently treats every member as equal. Gate item 5 requires
role-differentiated actions. The matrix below is the binding target from
`authorization-overview.html` section 05; do not invent extra tiers.

| Action in Studio | Minimum role | Why |
|---|---|---|
| View brands, projects, runs | (read tier: see note) | Reading costs nothing |
| Generate, run workflows | `member` | Spends provider budget |
| Create / edit brands, sessions | `member` | Core work |
| Delete brands / projects | `admin` | Destructive, rare |
| Mint / revoke company API keys | `owner` / `admin` | Machine credentials (already LIVE) |
| Billing, credits, spend | `billing_admin` + `owner` | Arrives with the billing slice |

**Read tier (SETTLED, and the role now EXISTS):** Marlin approved the
tenant-level `viewer` role on 2026-07-27 (gate item 10), it shipped in
auth-brain#73, and it is LIVE in the production FGA model as of 2026-07-28.
So wire the read tier to `viewer` directly, as the matrix says. There is no
placeholder branch to build any more.

What `viewer` means, so you gate on it correctly:
- It is the LOWEST rung on the company ladder and is READ-ONLY.
- `tenant.viewer = this OR member`, a SAME-SCOPE hierarchy: every
  member/admin/owner of a company is also a viewer of it. So a viewer-or-above
  check passes for all four roles, while a member-or-above check must FAIL for a
  plain viewer.
- It does NOT cascade across tiers: a company viewer gets nothing on the
  workspaces beneath it.

Do NOT invent a viewer role locally in Studio and do NOT special-case it in
scattered call sites. The policy module is the only place that knows which role
satisfies the read tier. Confirm the installed `@marlinjai/auth-brain-shared`
actually exposes the tenant `viewer` role before relying on it (published as
**1.6.0**; this repo pins something far older, so bump it and COMMIT the
lockfile).

## Where the roles come from

Roles arrive in the auth-brain verify payload, which by the time this slice runs
delivers EFFECTIVE roles (inherited via the FGA model) with a direct-vs-inherited
marker. Read roles ONLY from that payload. Do NOT call OpenFGA directly from
Studio and do NOT re-derive inheritance locally: one decision plane is the whole
point of decision 2. Confirm the SDK version in this repo actually delivers
effective roles before relying on them; if it does not, say so and stop.

## What to build

1. **Discover the real surface first.** Enumerate Studio's mutating entry points
   (route handlers and server actions): deletes, generation/workflow runs,
   brand/session create+edit, key minting. Produce that inventory before
   changing code, and put it in your final message. Do not guess at file paths.
2. **One policy module** declaring the matrix as data (action -> minimum role),
   the single source of truth in this repo. Every gate reads from it. No
   scattered inline role comparisons.
3. **Enforce at the server boundary**, not only in the UI. A hidden button is
   not authorization. Every action in the matrix gets a server-side check that
   fails closed.
4. **UI reflects the matrix**: actions a user cannot perform are disabled or
   hidden with an explanation, so the UI and the server agree. The server stays
   the authority.
5. **Declare the matrix to the suite-apps registry** so the auth-brain admin
   console can display it read-only (decision 3: matrices are policy-as-code per
   app, centrally VISIBLE, never centrally configurable). Find how the registry
   entry for `studio` is declared in auth-brain and add the matrix metadata in
   the shape that side expects. If that shape does not exist yet, say so and
   propose the minimal addition rather than inventing a parallel mechanism.

## Tests (required)

- Per matrix row: the minimum role is ALLOWED and the role one tier below is
  DENIED, at the server boundary.
- An inherited admin (from the company, per the B slice) is accepted exactly
  like a direct admin: inheritance must not be second-class.
- A plain company `member` with no direct workspace membership does NOT get
  workspace access (the B slice removes that cascade; assert Studio agrees).
- Fail-closed: unknown/absent role, missing grant, or a verify failure denies.

## Verification reality in THIS repo (read before you rely on a green gate)

lumitra-studio has **no CI verify workflow**. `.github/workflows/` contains only
`deploy.yml`, which builds and pushes an image. There is NO automated gate on a
pull request here, so whatever you run locally is the ONLY verification this
change will ever get. Treat that as a reason for more care, not less.

`pnpm test` in this repo is wrapped in `infisical run` (it needs injected env),
so it may not run in your environment. The goal's `verify` line is therefore
lint + build, which always runs. You must ALSO:

- run `pnpm test` if it works in your environment, and say plainly in your final
  message whether it ran and what the result was;
- if it cannot run, say so explicitly rather than implying the suite passed. Do
  NOT report a green build as though it were a green test suite.

Write the new tests regardless, so the operator can run them.

## Definition of done

- `pnpm lint` and `pnpm build` exit 0.
- The action inventory from step 1 is in your final message, with each entry
  mapped to its matrix row.
- No direct OpenFGA calls added to Studio.

## Constraints

- Do NOT add a `viewer` role. Do NOT build billing enforcement (that arrives
  with the billing slice); the billing row stays declared-but-unenforced.
- Do NOT change auth-brain in this slice except, if strictly required, the
  registry matrix metadata.
- Keep the diff proportionate: this is a policy layer plus call-site gating, not
  a refactor of Studio's routing.
