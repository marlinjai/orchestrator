import pytest

from textkit.csvutil import parse_row


def test_examples():
    assert parse_row('a,"b,c",d') == ["a", "b,c", "d"]
    assert parse_row('"say ""hi"" now"') == ['say "hi" now']
    assert parse_row("") == [""]
    assert parse_row("a,,b") == ["a", "", "b"]
    assert parse_row("a,") == ["a", ""]
    assert parse_row('x"y,z') == ['x"y', "z"]


def test_quoted_empty_and_spaces_kept():
    assert parse_row('"",b') == ["", "b"]
    assert parse_row(" a , b ") == [" a ", " b "]


def test_unterminated_quote_raises():
    with pytest.raises(ValueError):
        parse_row('"abc')


def test_junk_after_closing_quote_raises():
    with pytest.raises(ValueError):
        parse_row('"a"b,c')
