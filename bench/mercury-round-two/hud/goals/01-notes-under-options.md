---
verify: pnpm --filter @agentic-os/hud test
---
# Depth limit and hidden entries for `notesUnder`

Work in `apps/hud/src/lib/vault-export.ts`.

`notesUnder(nodes)` lists every note beneath a folder, in tree order. Give it an optional second
argument, `options?: { maxDepth?: number; skipHidden?: boolean }`. Without options, or with an
empty object, it behaves exactly as today.

## maxDepth

- `0`: only the notes that are directly in `nodes`; no directory is entered.
- `1`: also the notes directly inside the directories in `nodes`; and so on.
- `undefined`: no limit.
- Any other value that is not a non-negative integer (for example `-1`, `1.5`, `NaN`) makes
  the function throw a `RangeError`. This check happens before anything is listed, even when
  `nodes` is empty.

## skipHidden

When `true`, an entry whose `name` starts with `.` or `_` is skipped: a hidden file is not
listed, and a hidden directory is not entered at all (nothing beneath it is listed). When
`false` or left out, nothing is skipped.

The tree order of the result is unchanged, and only notes (names ending in `.md`, as
`isNoteName` decides) are listed.

Add or update tests for this behavior next to the module in `apps/hud/src/lib/` (files named
`*.test.ts`). Run `pnpm --filter @agentic-os/hud test` from the repository root until it passes,
then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit
with update_state. Do not change the behavior of anything the task does not mention.
