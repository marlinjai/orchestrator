---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Fix `slugify` in `textkit/strings.py`

`slugify` in `textkit/strings.py` leaves runs of dashes and leading or trailing dashes.
Fix it so that it: lowercases the text, turns every run of characters that are not
ASCII letters or digits into a single `-`, and strips `-` from both ends.

Examples: `slugify("  Hello,  World!! ")` is `"hello-world"`, `slugify("a--b")` is
`"a-b"`, `slugify("!!!")` is `""`, `slugify("")` is `""`, `slugify("Already-Fine")`
is `"already-fine"`, `slugify("Crème Brûlée")` is `"cr-me-br-l-e"`.

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
