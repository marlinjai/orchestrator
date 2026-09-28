import pytest

from textkit.strings import wrap


def test_examples():
    assert wrap("the quick brown fox", 10) == ["the quick", "brown fox"]
    assert wrap("abcdefghij", 4) == ["abcd", "efgh", "ij"]
    assert wrap("a bcdefg h", 3) == ["a", "bcd", "efg", "h"]


def test_whitespace_collapses():
    assert wrap("  a\n\n b\tc  ", 20) == ["a b c"]
    assert wrap("", 5) == []
    assert wrap("   \n ", 5) == []


def test_lines_never_exceed_width():
    text = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do"
    for width in range(1, 30):
        assert all(len(line) <= width for line in wrap(text, width))
        assert " ".join(wrap(text, width)).replace(" ", "") == text.replace(" ", "")


def test_bad_width():
    with pytest.raises(ValueError):
        wrap("a", 0)
