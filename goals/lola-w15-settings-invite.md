---
task: lola-w15-settings-invite
shared_state: [i18n]
verify: pnpm --filter @lola/web i18n:check && pnpm --filter @lola/web typecheck
verify_fix_cap: 2
---

# Goal

Remove the invite-users section from the family settings page. The product intent (PR #233 moved Settings into the profile dropdown) is to simplify settings; users invite from the family tree instead. This is the unfinished half of that card.

## Read first

- `apps/web/src/app/[locale]/families/[familyId]/settings/page.tsx` (:305-312 the invite form/title posting to `/families/:id/invites`; invite state at :34-108).
- The family-tree invite affordance (confirm an invite path exists there, e.g. components under `apps/web/src/components/family-tree/` or the family-tree page). If inviting from the family tree does NOT actually work, record that as an `open_thread` (do not leave the user with no way to invite).
- `apps/web/messages/de.json` / `en.json` for any now-orphaned invite-related keys under the settings namespace.

## Definition of done

- Remove the invite section from the settings page: the form JSX (:305-312), the handler, and the now-unused invite state (:34-108). No dead code, no unused imports, no dangling references left.
- Remove any settings-invite i18n keys that become orphaned, from BOTH de.json and en.json (keep parity).
- Confirm inviting from the family tree still works; if it does not, file an `open_thread` documenting the gap (do not create a dead end).
- `pnpm --filter @lola/web i18n:check` and `pnpm --filter @lola/web typecheck` pass.
- Single conventional commit describing the why.

## Constraints

- Stay in this worktree. Do not push to any remote. Touch only `apps/web` (settings page + messages, plus any directly-coupled cleanup).
- Edit messages JSON via parse -> stringify -> ascii-escape -> prettier; keep de/en parity. NO em-dash or en-dash.
- Output a final completion message.
