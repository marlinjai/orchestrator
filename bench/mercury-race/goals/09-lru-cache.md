---
verify: python3 -m pytest -q -p no:cacheprovider tests
---
# Add an LRU cache class in a new `textkit/cache.py`

Create `textkit/cache.py` with a class `LRUCache`:

- `LRUCache(capacity: int)`; a capacity below 1 raises `ValueError`;
- `put(key, value)` stores or replaces a value and marks the key most recently used;
  when inserting a NEW key would exceed the capacity, first evict the least recently
  used key;
- `get(key, default=None)` returns the value and marks the key most recently used,
  or returns `default` for a missing key (without changing any order);
- `len(cache)` is the number of stored keys; `key in cache` tests membership WITHOUT
  changing the usage order.

Add or update tests for this behavior under `tests/`. Run `python3 -m pytest -q tests` until it passes, then commit your change with git (`git add -A && git commit -m "<message>"`) and record the commit with update_state. Do not change the behavior of anything the task does not mention.
