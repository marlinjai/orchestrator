"""String helpers."""

import re


def slugify(text: str) -> str:
    """Lowercase ``text`` and replace every non-alphanumeric character with "-"."""
    return re.sub(r"[^a-z0-9]", "-", text.lower())


def truncate(text: str, width: int, ellipsis: str = "...") -> str:
    """Shorten ``text`` to ``width`` characters, marking the cut with ``ellipsis``."""
    if len(text) <= width:
        return text
    return text[:width] + ellipsis


def wrap(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError(width)
    words = []
    for w in text.split():
        words.extend(w[i : i + width] for i in range(0, len(w), width))
    lines, cur = [], ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
