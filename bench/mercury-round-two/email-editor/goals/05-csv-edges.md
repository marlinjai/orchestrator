---
verify: cd packages/contacts && pnpm exec vitest run
---
# CSV parsing edge cases: byte order mark, bare carriage returns, quoted whitespace

Work in `packages/contacts/src/csv-importer.ts`, in `parseCSV` and `detectDelimiter`.

## parseCSV

1. A byte order mark (`﻿`) at the very start of the content is ignored.
2. A bare carriage return (`\r` not followed by `\n`) ends a row, just like `\n` and `\r\n` do.
   Inside a quoted section a `\r` stays part of the field.
3. Whitespace inside quotes is kept. Today every field is trimmed, which destroys a value such as
   `" padded "`. The rule becomes:
   - A field is built from its unquoted parts and its quoted parts, in order.
   - Whitespace at the start of the field is removed only if the field starts with an unquoted
     part, and whitespace at the end only if it ends with an unquoted part.
   - Everything inside quotes is kept exactly, with `""` standing for one literal `"`.

   Examples (one field each): `" padded "` gives ` padded ` (with both spaces); `  "a"  ` gives
   `a`; `  x "y z"  ` gives `x y z`; `"a" b ` gives `a b`; `  plain  ` gives `plain`.
4. A row is dropped only when every one of its fields is the empty string, as today. A row
   holding a quoted field with only whitespace, such as `" "`, is not empty and is kept.

## detectDelimiter

1. A byte order mark at the start is ignored.
2. The first line ends at the first line break (`\n`, `\r\n` or a bare `\r`) that is outside
   quotes; a line break inside a quoted section does not end it.
3. Only delimiters outside quotes are counted. In `"Doe, John";age;city` the comma does not
   count, so the result is `;`.
4. The candidates stay `,`, `;`, tab and `|`, in that order, and a tie is won by the earlier one.
   With no delimiter at all the result is `,`.

Add or update tests for this behavior in `packages/contacts/src/__tests__/`. Run
`pnpm exec vitest run` inside `packages/contacts` until it passes, then commit your change with git
(`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change
the behavior of anything the task does not mention.
