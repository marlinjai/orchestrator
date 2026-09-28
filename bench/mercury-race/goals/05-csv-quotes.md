---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Make `parse_row` in `textkit/csvutil.py` handle quoted fields

`parse_row(line)` in `textkit/csvutil.py` splits on every comma. Make it follow the
RFC 4180 quoting rules for a single line:

- fields are separated by `,`;
- a field that starts with `"` is quoted: it runs to the matching closing `"`, may
  contain commas, and `""` inside it stands for one literal `"`;
- after a closing quote the next character must be `,` or the end of the line,
  otherwise raise `ValueError`; an unterminated quoted field raises `ValueError`;
- unquoted fields are taken literally (no trimming), and a `"` in the middle of an
  unquoted field is literal.

Examples: `parse_row('a,"b,c",d')` is `["a", "b,c", "d"]`, `parse_row('"say ""hi"" now"')`
is `['say "hi" now']`, `parse_row("")` is `[""]`, `parse_row("a,,b")` is `["a", "", "b"]`,
`parse_row('a,')` is `["a", ""]`, `parse_row('x"y,z')` is `['x"y', "z"]`.

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
