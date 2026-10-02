---
verify: pnpm --filter @agentic-os/hud test
---
# Start time for embedded YouTube links

Work in `apps/hud/src/lib/link-units.ts`, in `embedFor(url)`.

A YouTube link can carry a start time, for example `https://youtu.be/dQw4w9WgXcQ?t=1m30s` or
`https://www.youtube.com/watch?v=dQw4w9WgXcQ&start=90`. Today the player always starts at zero.
Carry the start time into the player URL.

## Reading the start time

Look at the query parameter `start` first, then `t`. The first of the two that holds a valid
value greater than zero is used; if neither does, there is no start time. A value is valid in one
of two shapes (matched case-insensitively, no surrounding or inner whitespace):

1. **Seconds**: one or more digits, optionally followed by `s`. `90` and `90s` both mean 90
   seconds.
2. **Parts**: an hours part `<digits>h`, a minutes part `<digits>m` and a seconds part
   `<digits>s`, each optional, in that order, with at least one of them present.
   `1m30s` is 90, `2h` is 7200, `1h5s` is 3605, `1h2m3s` is 3723.

Anything else is invalid: the empty string, `abc`, `1.5`, `-10`, `30m1h`, `1m 30s`,
`1h30`.

## The player URL

For a YouTube link with a start time of `N` seconds, the result's `src` is
`https://www.youtube-nocookie.com/embed/<id>?rel=0&start=N`. Without a start time it stays
`https://www.youtube-nocookie.com/embed/<id>?rel=0`, exactly as today. This applies to every
YouTube URL shape `embedFor` already accepts (`watch?v=`, `youtu.be/`, `shorts/`, `embed/`,
`live/`). `provider` and `video` are unchanged, and no other provider is affected: their
query parameters are still ignored.

Add or update tests for this behavior next to the module in `apps/hud/src/lib/` (files named
`*.test.ts`). Run `pnpm --filter @agentic-os/hud test` from the repository root until it passes,
then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit
with update_state. Do not change the behavior of anything the task does not mention.
