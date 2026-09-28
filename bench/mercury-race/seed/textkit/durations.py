"""Duration parsing."""

import re

_UNITS = {"h": 3600, "m": 60}


def parse_duration(text: str) -> int:
    """Parse a compact duration such as "1h30m" into seconds."""
    total = 0
    for amount, unit in re.findall(r"(\d+)([hm])", text):
        total += int(amount) * _UNITS[unit]
    return total
