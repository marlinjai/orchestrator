---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Add word wrapping to `textkit/strings.py`

Add `wrap(text: str, width: int) -> list[str]` to `textkit/strings.py`:

- words are separated by any whitespace; runs of whitespace (including newlines)
  collapse;
- lines are filled greedily with words joined by single spaces, never longer than
  `width`;
- a word longer than `width` is split into chunks of exactly `width` characters (the
  last chunk may be shorter), and each chunk behaves like a word;
- empty or whitespace-only text gives `[]`; `width < 1` raises `ValueError`.

Examples: `wrap("the quick brown fox", 10)` is `["the quick", "brown fox"]`,
`wrap("abcdefghij", 4)` is `["abcd", "efgh", "ij"]`, `wrap("a bcdefg h", 3)` is
`["a", "bcd", "efg", "h"]`.

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
