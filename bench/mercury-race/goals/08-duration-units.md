---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Fix `parse_duration` in `textkit/durations.py`

`parse_duration` in `textkit/durations.py` only understands `h` and `m` and silently
ignores anything else. Rewrite it so that:

- it accepts units `d` (86400 s), `h`, `m` and `s`, each at most once and in that
  order, each preceded by a non-negative integer: `"1d2h3m4s"` is 93784, `"45s"` is 45,
  `"90m"` is 5400, `"0s"` is 0, `"2h"` is 7200;
- anything else raises `ValueError`: the empty string, whitespace anywhere, unknown
  units, a unit without a number, a number without a unit, repeated units, and units
  out of order (`"1m1h"`).

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
