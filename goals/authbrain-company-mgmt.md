---
task: authbrain-company-mgmt
verify: pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1500
---

# Goal

Give a logged-in auth-brain user a way to create and manage ADDITIONAL companies (tenants) after signup. Today the only tenant a user ever gets is the one provisioned inside the signup transaction; a second company requires the admin console or the ADMIN_API_KEY machine API. This slice adds the user-facing surface: a session-authed API to create/list companies plus a `settings/companies` page. This is Slice 1 of the cross-repo "Studio company isolation" plan (Slice 2, in lumitra-studio, scopes Studio data by tenant and does NOT depend on this slice's code).

## Read first

- `packages/app/src/lib/flows/signup.ts` (the provisioning transaction you will extract and reuse; note `signUpInvited` creates NO personal group/tenant/workspace)
- `packages/app/migrations/002_tenants.sql` and `003_workspaces.sql` (tables, roles, uniqueness)
- `packages/app/src/app/api/invitations/route.ts` (the existing pattern for a session-authed + CSRF-protected user-facing API route; mirror its auth and CSRF handling exactly)
- `packages/app/src/app/api/sessions/verify/route.ts` and `src/lib/db/repositories/tenants.ts` (`listTenantsForUser`)
- `packages/app/src/app/settings/account/` (the existing settings page pattern to mirror for the new page)
- `packages/app/src/app/api/admin/machine/orgs/route.ts` (the admin provisioning path; reuse shared helpers where reasonable, do not fork a third copy of the provisioning SQL)
- `@marlinjai/auth-brain-shared` `RESERVED_TENANT_SLUGS`
- Repo CLAUDE.md / README for conventions

## Definition of done

1. **Extracted provisioning helper.** The "create tenant under a group" block (tenant + tenant_settings + owner tenant_membership + 'Main'/'main' workspace + admin workspace_membership + the matching outbox events) lives in ONE shared function (e.g. `src/lib/flows/provision.ts::provisionTenant(tx, { groupId, userId, name, slug })`) used by BOTH `signUpWithPassword` and the new route. No duplicated SQL. Signup behavior must remain byte-identical (same events, same roles).
2. **`POST /api/orgs`** (session cookie auth + CSRF, mirroring `api/invitations`): body `{ name, slug }`.
   - Validates: authenticated session; slug not in `RESERVED_TENANT_SLUGS`; slug not taken among live tenants (deleted_at IS NULL); name/slug shape validation consistent with signup's rules.
   - Resolves the caller's personal tenant_group (their `tenant_group_memberships` row with role owner/admin on a group with `is_personal = TRUE`).
   - UNHAPPY PATH THAT MUST WORK: an invited user has NO personal group (`signUpInvited` provisions none). In that case create one first (`is_personal = TRUE`, named from the email local-part, owner membership, `tenant_group.created` + membership outbox events, exactly like signup does) inside the same transaction, then create the tenant under it.
   - Creates the tenant via the extracted helper, appends an audit event, returns `201` with `{ group_id, tenant_id, workspace_id }`.
   - Error responses are explicit JSON with status codes (400 validation, 401 unauthenticated, 409 slug taken); no silent failures.
3. **`GET /api/orgs`** (session auth): returns the caller's tenants with roles (reuse `listTenantsForUser`). 401 when unauthenticated.
4. **`settings/companies` page**: lists the user's companies with their role; a create-company form (name + slug) posting to `POST /api/orgs`; a "set active" action per company calling the existing `POST /api/sessions/active-context`; a link/hint for inviting a member to a company (the existing invitations flow with `scope_type=tenant`). Match the visual/structural conventions of `settings/account`. Surface API errors to the user (slug taken, reserved slug); no dead-end states.
5. **Tests** (vitest, same style as existing flow tests):
   - create company happy path: tenant + settings + owner membership + workspace + admin membership + outbox events all present
   - invited user with no personal group: group auto-created with owner membership, then tenant under it
   - reserved slug -> 400; taken slug -> 409; unauthenticated -> 401; CSRF failure rejected
   - re-entry: creating a second company leaves the first company and its memberships untouched, and `GET /api/orgs` lists both with correct roles
   - signup regression: existing signup tests still green (the extraction changed no behavior)
6. `pnpm test && pnpm typecheck && pnpm lint` green at repo root.
7. Single conventional commit on this branch explaining the WHY (user-facing multi-company creation; Slice 1 of Studio company isolation).

## Constraints

- Stay in this worktree. Do not modify files outside it. Do not push.
- Do NOT touch the SDK or shared package's published API surface; the session payload already carries `tenants[]` and nothing here changes it. (If a type must be exported for the app, keep it app-local.)
- Do NOT change signup semantics, the invitations flow, or the admin machine API contracts.
- Do NOT add an email-verification requirement gate to the new route beyond what existing session-authed routes enforce (stay consistent with `api/invitations`).
- No em-dashes or en-dashes anywhere in code, comments, or the commit message.
- When done, output a final message that the task is complete.

## Notes

- This is production auth infra: fail closed everywhere, never log tokens/cookies/password material (mirror the discipline visible in `verifyRequest`-style code and existing routes).
- The workspace auto-created per company is deliberately the same 'Main'/'main' shape signup creates; Studio (Slice 2) scopes by tenant, not workspace, so no workspace naming cleverness is needed.
