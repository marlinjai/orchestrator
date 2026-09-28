---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Add `word_count` to `textkit/strings.py`

Add a function `word_count(text: str) -> int` to `textkit/strings.py`.

A word is a maximal run of letters, digits and apostrophes (`'`). Everything else
separates words. Examples: `word_count("")` is 0, `word_count("Hello, world!")` is 2,
`word_count("don't stop")` is 2, `word_count("a1 b2--c3")` is 3,
`word_count("   ")` is 0. Letters include non-ASCII letters (`"über café"` is 2).

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
