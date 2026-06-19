---
task: lola-w01-summary-i18n
shared_state: [i18n]
verify: pnpm --filter @lola/web i18n:check && pnpm --filter @lola/web typecheck
verify_fix_cap: 2
---

# Goal

Fix the story-dashboard "About this story" summary rendering a hardcoded English sentence on the German flow. It must use a localized i18n key so `/de` shows German and `/en` stays English.

## Read first

- `apps/web/src/app/[locale]/families/[familyId]/stories/[storyId]/dashboard/page.tsx` around lines 693-701 (the hardcoded `A personalized story for {names}.` JSX) and the surrounding `useTranslations('storyDashboard')` usage.
- `apps/web/messages/de.json` and `apps/web/messages/en.json` (the `storyDashboard` namespace; note there is no `personalizedFor` key yet).
- The repo CLAUDE.md and the existing `t.rich(...)` call-site style in this file.

## Definition of done

- Add `storyDashboard.personalizedFor` to BOTH `apps/web/messages/en.json` (`"A personalized story for {names}."`) and `de.json` (`"Eine persoenliche Geschichte fuer {names}."`).
- Replace the hardcoded JSX sentence with `t.rich('personalizedFor', ...)` preserving the bold names span and the `" & "` join, matching the existing `t.rich` call-site style in this file.
- `/de` renders the German sentence; `/en` unchanged.
- The `children.length === 0` guard that suppresses the sentence is preserved.
- A grep for the literal `A personalized story for` in `apps/web/src` returns nothing.
- `pnpm --filter @lola/web i18n:check` passes (de/en parity) and `pnpm --filter @lola/web typecheck` passes.
- Single conventional commit describing the why.

## Constraints

- Stay in this worktree. Do not push to any remote. Do not modify files outside `apps/web`.
- Edit the messages JSON via parse -> add key -> stringify -> ascii-escape -> prettier (the repo's convention enforced by `i18n:check`). Keep de/en in parity.
- NO em-dash or en-dash anywhere. German copy uses "ue/oe/ae" only if that matches the existing file style; otherwise use proper umlauts as the file already does. Match the file.
- When done, output a final message that the task is complete.
