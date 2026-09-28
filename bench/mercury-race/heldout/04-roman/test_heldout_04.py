import pytest

from textkit.roman import from_roman, to_roman


def test_known_values():
    cases = {1: "I", 4: "IV", 9: "IX", 14: "XIV", 40: "XL", 90: "XC", 400: "CD",
             900: "CM", 1994: "MCMXCIV", 2024: "MMXXIV", 3999: "MMMCMXCIX"}
    for n, s in cases.items():
        assert to_roman(n) == s
        assert from_roman(s) == n


def test_round_trip_all():
    for n in range(1, 4000):
        assert from_roman(to_roman(n)) == n


@pytest.mark.parametrize("bad", [0, -1, 4000, 2.5, True, "5"])
def test_to_roman_rejects(bad):
    with pytest.raises(ValueError):
        to_roman(bad)


@pytest.mark.parametrize("bad", ["", "iv", "IIII", "IC", "VX", "MMMM", "ABC", "XM"])
def test_from_roman_rejects(bad):
    with pytest.raises(ValueError):
        from_roman(bad)
