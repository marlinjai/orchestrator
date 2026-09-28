import pytest

from textkit.durations import parse_duration


def test_valid():
    assert parse_duration("1d2h3m4s") == 93784
    assert parse_duration("45s") == 45
    assert parse_duration("90m") == 5400
    assert parse_duration("0s") == 0
    assert parse_duration("2h") == 7200
    assert parse_duration("1h30m") == 5400


@pytest.mark.parametrize("bad", ["", " 1h", "1h 30m", "1x", "h", "10", "1h1h", "1m1h", "1s1m", "-1h", "1.5h"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)
