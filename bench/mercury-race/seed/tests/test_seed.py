from textkit.csvutil import parse_row
from textkit.durations import parse_duration
from textkit.strings import slugify, truncate


def test_slugify_simple():
    assert slugify("hello") == "hello"


def test_truncate_short_text_is_unchanged():
    assert truncate("abc", 10) == "abc"


def test_parse_duration_hours_and_minutes():
    assert parse_duration("1h30m") == 5400


def test_parse_row_plain():
    assert parse_row("a,b,c") == ["a", "b", "c"]
