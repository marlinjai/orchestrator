import pytest

from textkit.cache import LRUCache


def test_capacity_validation():
    with pytest.raises(ValueError):
        LRUCache(0)


def test_eviction_order():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1  # a is now most recent
    c.put("c", 3)  # evicts b
    assert "b" not in c
    assert c.get("a") == 1 and c.get("c") == 3
    assert len(c) == 2


def test_replace_does_not_evict_and_refreshes():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 10)  # replace, a most recent
    assert len(c) == 2
    c.put("c", 3)  # evicts b
    assert c.get("a") == 10
    assert "b" not in c


def test_contains_does_not_refresh():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert "a" in c
    c.put("c", 3)  # a is still least recent
    assert "a" not in c


def test_missing_get_returns_default_without_side_effects():
    c = LRUCache(1)
    c.put("a", 1)
    assert c.get("zzz", 42) == 42
    assert c.get("zzz") is None
    assert len(c) == 1 and c.get("a") == 1
