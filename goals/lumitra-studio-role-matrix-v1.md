---
task: lumitra-studio-role-matrix-v1
spec: auth-brain docs/internal/authorization-overview.html section 05 + docs/plans/2026-07-24-authz-hardening.md decision 3
depends_on: [auth-brain-bsync-inheritance-v2]
verify: pnpm build && pnpm typecheck && pnpm lint && pnpm test
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

**Read tier note (DECIDED 2026-07-27):** Marlin approved the tenant-level
`viewer` role, so pre-launch gate item 10 is settled: viewer is WANTED.

However, the role must exist in auth-brain before Studio can gate on it
(`TenantRole` currently unions `owner|admin|billing_admin|member`; only
`workspace` has a `viewer`). Sequencing:

- If the auth-brain tenant-level `viewer` role has ALREADY shipped when you run,
  wire the read tier to `viewer` as the matrix says.
- If it has NOT, build the matrix with the read tier gated at `member`, but
  declare the viewer row in the policy module as a first-class entry marked
  pending, so switching it on is a one-line change and not a re-design.

Either way: do NOT invent a viewer role locally in Studio, and do NOT
special-case it in scattered call sites. The policy module is the only place
that knows which role satisfies the read tier.

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

## Definition of done

- Verify chain (mirroring CI: build, typecheck, lint, test) exits 0.
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
