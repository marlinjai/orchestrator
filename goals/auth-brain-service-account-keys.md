---
task: auth-brain-service-account-keys
spec: docs/superpowers/specs/2026-06-16-service-account-api-keys.md
shared_state: [migrations]
verify: pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Implement the leaf spec at `docs/superpowers/specs/2026-06-16-service-account-api-keys.md`:
auth-brain's v1.5 principal-owned API-key surface. Add **service-account principals** scoped
at one of three tiers (`tenant_group` = account/org-wide, `tenant`, `workspace` = project),
**issuable/revocable API keys** tied to a service account, and a **fail-closed
`verifyApiKey`** endpoint, on auth-brain's existing postgres.js + OpenFGA stack. Storage Brain
is the first consumer (a later slice). This is **additive only**: `ADMIN_API_KEY` and
`SERVICE_TOKEN` must keep working unchanged.

## Read first

- The spec file in full (Model, three scope tiers, migration 007, OpenFGA changes, outbox
  events, endpoints, fail-closed contract, SDK changes, file list, tests, out-of-scope).
- The parent plan `docs/superpowers/plans/2026-06-16-centralized-api-keys-and-storage-brain-upload.md`
  for why this slice exists and what it deliberately does NOT do.
- Existing patterns to copy exactly:
  - Machine routes: `packages/app/src/app/api/admin/machine/memberships/route.ts` and
    `.../orgs/route.ts` (the `requireAdminApiKey` → Zod → resolve actor by email → flow →
    `handleRouteError` shape).
  - Crypto: import `generateApiKey`, `hashApiKey`, `verifyApiKey` from `@marlinjai/brain-core`
    (`sk_live_` prefix, SHA-256 hex). Do NOT add bcrypt or a second key format.
  - Tuple sync: `packages/app/src/lib/openfga/sync-worker.ts` (`grantTuples`) + `schema.json`.
  - DB repos + migrations convention under `packages/app/src/lib/db/repositories/` and
    `packages/app/migrations/` (next number is 007; raw SQL, postgres.js template literals).
  - Tests: `packages/app/src/lib/admin-auth.spec.ts` (vitest + `@testcontainers/postgresql`)
    and `packages/sdk/src/client.spec.ts` (mocked fetch).

## Definition of done

Everything in the spec's body, plus the standing gates:

- `pnpm run build && pnpm run typecheck && pnpm run lint && pnpm test` all pass. The DB-touching
  tests use testcontainers and need Docker (it is available). A testcontainer failure is a real
  failure — do NOT mock around it or skip integration tests to make the gate green.
- The three-tier OpenFGA isolation test from the spec MUST exist and pass: an account-wide
  (`tenant_group`) key passes `can()` for a child tenant and grandchild workspace, and FAILS
  for a resource in a different `tenant_group`.
- The `verifyApiKey` fail-closed test MUST exist: a simulated DB error returns 401, never 200/500.
- Spec frontmatter `status: draft` → `status: done`.
- If there is a STATUS/ROADMAP index row to update, use the existing column format exactly
  (no new columns, no reformatting).
- Single commit, conventional-commit message describing the WHY.

## Constraints

- Stay in this worktree. Do not modify files outside it. Do not push to any remote.
- Additive only: do not change or remove the `ADMIN_API_KEY` or `SERVICE_TOKEN` paths, and do
  not alter the existing `verifySession` / `can()` behavior for `user:` subjects. Extending
  `can()` with an optional `subjectType` must keep every existing call working unchanged.
- Plaintext API keys are returned exactly once at issue time. Never store plaintext, never log
  a key, never put one in an error body or test snapshot.
- No em-dashes or en-dashes in any code, comment, or doc you write.
- Do NOT do slices 2/3 (Storage Brain consumption, dashboard upload) or workstream 4
  (dropping Storage Brain tables / physical partitioning). Out of scope.

## Notes

- No new runtime env vars are required; reuse existing `ADMIN_API_KEY`, `DATABASE_URL`,
  OpenFGA config.
- If the build needs Infisical-injected env at build time, that is the repo's existing
  pattern, not a regression; the verify gate runs plain commands and Docker-backed tests.
- File anything genuinely out of scope you discover as an `open_thread`, do not bury a bare
  TODO in the code.
- The repo's husky pre-commit hook runs `pnpm typecheck && pnpm lint` over the whole workspace
  and BLOCKS the commit on failure. Run `pnpm -r build` (so `@marlinjai/auth-brain-shared` and
  `-sdk` emit their `dist/`) and make typecheck + lint clean BEFORE you `git commit`, otherwise
  the commit is rejected. Do not bypass the hook with `--no-verify`; make it actually pass.
