"""String helpers."""

import re


def slugify(text: str) -> str:
    """Lowercase ``text`` and replace every non-alphanumeric character with "-"."""
    return re.sub(r"[^a-z0-9]", "-", text.lower())


def truncate(text: str, width: int, ellipsis: str = "...") -> str:
    """Shorten ``text`` to ``width`` characters, marking the cut with ``ellipsis``."""
    if width < 0:
        raise ValueError("width must be >= 0")
    if len(text) <= width:
        return text
    if width < len(ellipsis):
        raise ValueError("width shorter than ellipsis")
    return text[: width - len(ellipsis)] + ellipsis
