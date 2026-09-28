---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Add Roman numeral conversion in a new `textkit/roman.py`

Create `textkit/roman.py` with two functions:

- `to_roman(n: int) -> str` converts 1 to 3999 into standard uppercase Roman numerals
  using subtractive notation (`4` is `"IV"`, `9` is `"IX"`, `40` is `"XL"`, `90` is
  `"XC"`, `400` is `"CD"`, `900` is `"CM"`; `1994` is `"MCMXCIV"`, `3999` is
  `"MMMCMXCIX"`). Anything outside 1..3999, and any non-int (including `bool`),
  raises `ValueError`.
- `from_roman(s: str) -> int` is the exact inverse: it accepts only the canonical
  uppercase form that `to_roman` produces and raises `ValueError` for anything else
  (lowercase, empty string, `"IIII"`, `"IC"`, `"VX"`, `"MMMM"`).

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
