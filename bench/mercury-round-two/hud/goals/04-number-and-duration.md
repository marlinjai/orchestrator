---
verify: pnpm --filter @agentic-os/hud test
---
# More number spellings and a duration parser for database cells

Work in `apps/hud/src/lib/vault-database-values.ts`.

## numberOf

`numberOf(value)` reads a cell as a number. Keep everything it accepts today and add:

- **Accounting negatives.** A value wrapped in one pair of parentheses is negative:
  `"(1,234.50)"` is `-1234.5`, `"(12%)"` is `-12`, `"( 3 )"` is `-3`. If the text inside
  the parentheses already carries a sign (`+`, `-` or the Unicode minus), the result is
  `null`. Parentheses that do not wrap the whole trimmed value give `null`, as today.
- **Unicode minus.** A leading `−` (U+2212) means the same as `-`: `"−3,5"` is `-3.5`.
- **Apostrophe groups.** `'` (U+0027) and `’` (U+2019) are thousands separators and are
  removed: `"1'234.5"` is `1234.5`, `"12’000"` is `12000`.

## durationOf (new export)

`durationOf(value: string): number | null` reads a cell as a duration and returns it in
seconds, or `null` when it is not one. The value is trimmed first and matched
case-insensitively. Two forms are accepted:

1. **Unit form**: one or more parts, each a number directly followed by a unit, with optional
   whitespace between parts. Units are `d` (86400 seconds), `h` (3600), `m` (60) and `s` (1).
   A number is digits with an optional decimal part after a dot (`1`, `1.5`, `0.25`); it is
   never negative. Each unit appears at most once, and the units must come in the order
   `d`, `h`, `m`, `s`. Examples: `"1h 30m"` is `5400`, `"90m"` is `5400`, `"1.5h"`
   is `5400`, `"2d"` is `172800`, `"1D 2H 3M 4S"` is `93784`, `"45s"` is `45`,
   `"0.5s"` is `0.5`.
2. **Clock form**: `H:MM:SS` or `M:SS`. The first number is one or more digits; every later
   number is exactly two digits between `00` and `59`. Examples: `"1:30:00"` is `5400`,
   `"2:05"` is `125`, `"100:00"` is `6000`, `"0:00:07"` is `7`.

Everything else is `null`: the empty string, `"1h1h"`, `"30m 1h"` (wrong order), `"1:60"`,
`"1:5"`, `"1:00:00:00"`, `"-5m"`, `"5"`, `"5 m"` (a space between number and unit),
`"1h30"`, `"abc"`.

Add or update tests for this behavior next to the module in `apps/hud/src/lib/` (files named
`*.test.ts`). Run `pnpm --filter @agentic-os/hud test` from the repository root until it passes,
then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit
with update_state. Do not change the behavior of anything the task does not mention.
