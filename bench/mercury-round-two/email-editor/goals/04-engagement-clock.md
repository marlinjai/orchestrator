---
verify: cd packages/analytics && pnpm exec vitest run
---
# A fixed clock and robust timestamps in engagement scoring

Work in `packages/analytics/src/engagement.ts`.

## calculateEngagementScore

New signature: `calculateEngagementScore(events, weights = DEFAULT_WEIGHTS, now = Date.now())`,
where `now` is a `Date` or a number of milliseconds since the epoch. The recency decay is computed
against `now` instead of the current time, so a caller can score against a fixed moment.

- An event whose `timestamp` cannot be parsed (`new Date(timestamp).getTime()` is `NaN`) is
  skipped: it adds nothing to the score.
- An event whose timestamp lies after `now` counts with a decay factor of exactly `1`, never more.
- Everything else stays: decay factor `max(0, 1 - daysSince / recencyDecayDays)`, the weights, the
  rounding and the clamp to the range 0 to 100.

## buildContactEngagement

New signature: `buildContactEngagement(contactId, events, weights?, now?)`. `now` is passed on to
`calculateEngagementScore`.

`lastOpenAt` and `lastClickAt` must be the timestamp of the latest event of that type by its
parsed time, not by string comparison (timestamps may carry different time zone offsets). Events
whose timestamp cannot be parsed are ignored for this purpose; if no event of the type has a
parseable timestamp the field is `undefined`. The returned value is the original timestamp string
of the chosen event, unchanged. When two events have the same parsed time, the one that comes
first in the array wins.

`totalOpens` and `totalClicks` keep counting every event of the type, parseable or not.

Add or update tests for this behavior in `packages/analytics/src/__tests__/`. Run
`pnpm exec vitest run` inside `packages/analytics` until it passes, then commit your change with git
(`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change
the behavior of anything the task does not mention.
