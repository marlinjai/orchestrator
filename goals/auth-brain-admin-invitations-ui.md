---
task: auth-brain-admin-invitations-ui
shared_state: [lockfile, workspace]
verify: pnpm build && pnpm test && pnpm typecheck && pnpm lint
verify_fix_cap: 2
verify_timeout_s: 1800
---

# Goal

Build `packages/app/src/app/admin/invitations/page.tsx`, an admin console page for managing pending organization invitations. The machine API is already fully built (`packages/app/src/app/api/admin/machine/invitations/route.ts`); this is a UI-only slice, no backend changes. Read the intent stub `knowledge-base/backlog/intents/auth-brain-admin-invitations-ui.md` (repo-relative from `~/software-dev/knowledge-base/`) first for full context: this is launch-relevant because inviting a paying customer's teammate currently has to go through the raw machine API, which isn't a shippable admin experience.

## Read first

- `packages/app/src/app/api/admin/machine/invitations/route.ts` (the existing API surface: list pending, invite by email, revoke, whatever it actually exposes, read it exactly rather than assuming the shape)
- `packages/app/src/app/admin/users/page.tsx` and `packages/app/src/app/admin/orgs/page.tsx` (the sibling admin pages, mirror their layout/table/action patterns for consistency, this must look like it belongs)
- `packages/app/src/app/admin/layout.tsx` and `lib/admin-auth.ts` (the platform-admin gating this page must sit behind, same as every other admin page)
- Whatever confirm-dialog / toast pattern the sibling admin pages use for revoke (a destructive-ish action), reuse it rather than inventing a new one or using a native `window.confirm`

## Definition of done

- `/admin/invitations` page: list pending invitations, invite by email (form), revoke (with confirmation, reusing the existing branded dialog pattern, not `window.confirm`)
- Matches the visual language and interaction patterns of the sibling `/admin/users` and `/admin/orgs` pages exactly (same table style, same action-button treatment, same loading/error/empty states)
- Linked from the admin console's nav/sidebar wherever `/admin/users` etc. are linked from
- `pnpm build && pnpm test && pnpm typecheck && pnpm lint` all pass
- Single commit, conventional-commit message

## Constraints

- Stay in this worktree. Do not modify files outside it.
- Do not push to any remote.
- Do not touch the machine API route, this is UI-only.
- No native `window.confirm`/`alert`/`prompt` anywhere.

## Notes

Optional, lower priority, only if time allows after the page is done and verified: `docs/superpowers/plans/2026-06-07-admin-console-sketch.md` and `2026-06-07-embedded-vs-redirect-login.md` both claim the admin console lives in the suite-dashboard; reality is it shipped inside auth-brain itself. Either correct that claim in both docs (one line each) or set their frontmatter `status: archived`. Do this as a second commit on the same branch, not instead of the main task.
