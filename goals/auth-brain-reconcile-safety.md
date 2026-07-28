---
task: auth-brain-reconcile-safety
spec: docs/plans/2026-07-24-authz-hardening.md decision 2 (B-sync reconciliation)
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test && pnpm build
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal: two production defects in the new reconciliation job

Both found on live production within an hour of the B-sync deploy (auth-brain#69).
Fix both; they are small and independent.

## Defect 1 (SEVERE): `--heal` would delete the platform admin tuple and lock the console

`lib/openfga/reconcile.ts` builds its EXPECTED tuple set purely from Postgres
(`tenant_group_memberships`, `tenant_memberships`, `workspace_memberships`,
`tenant_groups`, `tenants`, `workspaces`, `service_accounts`). Anything in
OpenFGA that is not in that set is classed `orphanInFga` and, under
`heal: true`, DELETED.

The platform-admin grant has NO Postgres backing BY DESIGN.
`lib/openfga/seed-platform-admin.ts` says so explicitly: "Phase 1 has no SQL
`platform_admins` table, so this is the bootstrap path." The tuple
`user:<id>#admin@platform:lumitra` is written straight to FGA and is the ONLY
thing gating the `/admin` console (`lib/admin-auth.ts`, `PLATFORM_OBJECT`).

Live proof: production currently reports an open finding
`missing_side=postgres, scope_type=platform, role=admin` for the real platform
admin user. Running `openfga:reconcile -- --heal` today would delete that tuple
and lock the operator out of the admin console.

**Fix:** reconciliation must treat the `platform` type as OUT OF SCOPE on BOTH
sides. It is not Postgres-derived, so it can be neither "missing in FGA" nor an
"orphan". Filter `platform:` objects out of the actual/orphan set (and never
synthesize them into the expected set). Put the reason in a comment citing
seed-platform-admin.ts, so nobody re-adds it later.

Be precise: exclude by the object's TYPE being `platform`, not by a substring
match on the id.

## Defect 2: the findings table grows 26 rows per minute, forever

The job is wired as a loop in `workers/outbox-sync.ts` and INSERTS a fresh row
per mismatch on every pass. Measured on production: 832 rows in 31 minutes,
exactly 26 new rows every minute, for the SAME 26 unresolved mismatches. That is
~37k rows/day on the identity database for a set that has not changed.

**Fix:** a still-open finding must not be re-inserted. Keep ONE open row per
distinct mismatch, keyed by (`scope_type`, `scope_id`, `subject_id`, `role`,
`missing_side`) where `resolved_at IS NULL`. On a later pass:
- mismatch still present -> leave the existing open row (optionally bump a
  `last_seen_at` column if you add one; a migration is acceptable here);
- mismatch gone -> set `resolved_at`, exactly as today.

Add the appropriate partial unique index so the invariant is enforced by the
database, not only by application code, and make the write path idempotent
against it (an upsert / `ON CONFLICT DO NOTHING` or equivalent). A new migration
`013` is fine; do NOT rewrite migration `012` (it is already applied in prod).

Consider whether the existing ~800 duplicate rows should be collapsed by that
migration. If you do collapse them, keep the OLDEST open row per distinct
mismatch so `detected_at` still reflects when the problem actually started, and
say so in your final message.

## Tests (required)

- A `platform:` tuple present in FGA with no Postgres backing is NOT reported as
  an orphan and is NOT deleted under `heal: true`. Assert the delete call does
  not include it.
- Genuine orphans (a workspace membership tuple whose Postgres row is gone) ARE
  still reported and still deleted under heal: the fix must not blunt the GC.
- Running `reconcileOnce` twice over an unchanged mismatch leaves exactly ONE
  open finding row, not two.
- A mismatch that disappears between passes gets `resolved_at` set.
- Existing reconciliation coverage keeps passing; do not weaken it.

## Definition of done

- Verify chain in the frontmatter exits 0.
- `pnpm --filter @auth-brain/app test:integration` if docker is available; say so
  explicitly if it is not (CI is the gate).
- Final message states whether you collapsed the existing duplicate rows.

## Constraints

- Do NOT change the dual-write path, the FGA model, the verify payload, or the
  worker's other two loops.
- Do NOT make healing the default; it stays opt-in.
- This is the live identity service: smallest correct diff.
