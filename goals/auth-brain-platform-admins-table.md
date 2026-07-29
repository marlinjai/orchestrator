---
task: auth-brain-platform-admins-table
spec: orchestrator goals/HANDOVER-analytics-multi-company.md slice S5 (Marlin authorised the whole chain 2026-07-29)
depends_on: [auth-brain-active-scope-endpoint]
shared_state: [migrations]
verify: pnpm --filter @marlinjai/auth-brain-shared build && pnpm --filter @marlinjai/auth-brain-sdk build && pnpm typecheck && pnpm lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 2400
---

# Goal: give platform admins a real `platform_admins` table

Independent hygiene, but it removes a permanent special case that currently makes
`reconcile --heal` unsafe by convention rather than by construction.

## The problem

`packages/app/src/lib/openfga/seed-platform-admin.ts` writes
`user:<id>#admin@platform:lumitra` **straight to OpenFGA** with no Postgres
backing, because "Phase 1 has no SQL `platform_admins` table". The admin console
gate (`packages/app/src/lib/admin-auth.ts`, `PLATFORM_OBJECT = 'platform:lumitra'`)
then authorises against that tuple via `check()`.

Because Postgres never implies that tuple, the reconciler would class it an
orphan and **`--heal` would DELETE it, locking the operator out of the admin
console**. That nearly happened for real (auth-brain#70). The current fix is a
hardcoded type exclusion in `packages/app/src/lib/openfga/reconcile.ts:40`
(`PLATFORM_TYPE = 'platform'`), applied at line ~112 by filtering the actual set
before diffing.

So today the safety of `--heal` rests on a hardcoded string. That is the thing to
retire.

## What to build

### 1. The table

New migration (next number after `014_tenant_viewer_role.sql`) in
`packages/app/migrations/`. Follow the existing file conventions exactly.

`platform_admins` should carry at minimum: `user_id` (FK to users), the platform
`relation`, `created_at`, and a soft-delete column consistent with the rest of
the schema (`deleted_at`), since `expectedTuplesFromPostgres` derives everything
from `deleted_at IS NULL` rows.

**The relation is not just `admin`.** `admin-auth.ts` uses two platform relations:
`admin` (write console) and `auditor` (read-only). Model both, and constrain the
column to those values.

### 2. Seed through the table, with a B-sync dual write

Standing decision 2 is B-sync: membership/grant writes hit Postgres **and**
OpenFGA synchronously in the same request, loud on failure. `seed-platform-admin.ts`
must follow that rule instead of being an FGA-only side door: insert/upsert the
row AND write the tuple. Make it idempotent — the operator will re-run it.

Keep its existing CLI ergonomics (accepts a UUID or an email). Extend it to take
the relation, defaulting to `admin` so existing invocations keep working.

### 3. Teach the reconciler about platform tuples

`expectedTuplesFromPostgres` must synthesize the platform tuples from the new
table, exactly as it does for the other tiers. Then the type exclusion can go.

**Do NOT simply delete the exclusion and call it done.** If the table is empty
(or its query breaks), a full reconciliation would classify the live platform
tuple as an orphan and `--heal` would delete it — reintroducing the exact
lockout the exclusion exists to prevent, but silently.

Replace the hardcoded special case with a **principled, general guard**:

> Never GC orphans of an object TYPE for which Postgres produced **zero** expected
> tuples.

That is a real invariant, not a special case: a scope class with no source rows
almost always means a broken/empty query, not that every live tuple of that class
is garbage. It protects `platform` while the table is still empty, it protects
every other type against the same failure mode, and once the table is backfilled
platform reconciles fully and normally with no type named anywhere in the code.
Log loudly when the guard suppresses a deletion so an empty table is visible
rather than silent.

Missing-tuple reporting (the write direction) should NOT be suppressed by the
guard — a missing platform tuple is safe to report and safe to heal.

If you conclude this guard is wrong, STOP and escalate with your reasoning rather
than shipping a bare exclusion removal.

### 4. Keep the console working

`admin-auth.ts` authorises via `check()` against OpenFGA. That can stay — FGA
remains the decision engine (decision 2). The table is the **source of truth for
what should exist**, not a second decision plane. Do not add a Postgres-based
authorization path alongside the FGA one; that would create exactly the
dual-plane divergence this architecture exists to avoid.

## Tests (required)

- `expectedTuplesFromPostgres` synthesizes platform tuples from the table,
  including the `auditor` relation, and excludes soft-deleted rows.
- Reconciliation with a **populated** table: a platform tuple present in both is
  clean; one missing in FGA is reported (and healed); a genuine platform orphan
  (in FGA, not in the table) IS reported and IS GC'd.
- Reconciliation with an **empty** table: the live platform tuple is NOT deleted
  under `--heal` (the zero-expected guard), and the suppression is logged.
- The general guard is genuinely general: assert it also suppresses orphan GC for
  a non-platform type whose expected set came back empty.
- The seed script writes both Postgres and FGA, and is idempotent on re-run.
- `packages/app/src/lib/openfga/reconcile.spec.ts` already covers the current
  defect-1 behaviour. Update it to the new model rather than deleting its intent —
  the property "a `--heal` never locks the operator out of the console" must
  still be asserted.

## Definition of done

- The frontmatter verify chain exits 0 (mirrors `.github/workflows/ci.yml` minus
  the integration step, which needs a live Postgres service).
- Also run `pnpm --filter @auth-brain/app test:integration` (needs `DATABASE_URL`
  + docker). There is a `migrations.spec.ts` integration test — make sure the new
  migration is covered by whatever that asserts. If docker is unavailable, say so
  explicitly; CI gates it.
- **Your final message must state the exact operator backfill command** to run
  against production after deploy (seeding the live platform admin into the new
  table), and must warn that `reconcile --heal` should not be run in production
  until that backfill is done and `reconcile` reports zero platform findings.

## Constraints

- This is the **live central identity service**. Smallest correct diff.
- Do NOT change the FGA model (`schema.json`). The `platform` type and its
  `admin`/`auditor` relations already exist; this slice adds no model change and
  therefore needs no manual model push. If you think it does, STOP and escalate.
- Do NOT touch the active-scope / verify work from the sibling slice.
- Do NOT touch analytics, Studio, or storage-brain.
- Do NOT weaken or delete existing tests to make the suite green.
