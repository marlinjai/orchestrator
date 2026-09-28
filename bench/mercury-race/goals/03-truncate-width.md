---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Fix `truncate` in `textkit/strings.py`

`truncate(text, width, ellipsis="...")` in `textkit/strings.py` returns results longer
than `width`. Fix it so that:

- if `len(text) <= width`, it returns `text` unchanged;
- otherwise it returns `text[: width - len(ellipsis)] + ellipsis`, so the result is
  exactly `width` characters long;
- if `width < len(ellipsis)` and the text is longer than `width`, it raises `ValueError`;
- a negative `width` always raises `ValueError`.

Examples: `truncate("hello world", 8)` is `"hello..."`, `truncate("hello", 5)` is
`"hello"`, `truncate("hello", 4, ellipsis="~")` is `"hel~"`, `truncate("", 0)` is `""`.

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
