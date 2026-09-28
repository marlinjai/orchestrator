import pytest

from textkit.strings import truncate


def test_examples():
    assert truncate("hello world", 8) == "hello..."
    assert truncate("hello", 5) == "hello"
    assert truncate("hello", 4, ellipsis="~") == "hel~"
    assert truncate("", 0) == ""


def test_result_is_exactly_width():
    for width in range(3, 12):
        assert len(truncate("abcdefghijklmnop", width)) == width


def test_width_below_ellipsis_raises():
    with pytest.raises(ValueError):
        truncate("hello", 2)


def test_negative_width_raises():
    with pytest.raises(ValueError):
        truncate("", -1)
    with pytest.raises(ValueError):
        truncate("hello", -5)


def test_empty_ellipsis():
    assert truncate("hello", 3, ellipsis="") == "hel"
