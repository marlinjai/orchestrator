"""Minimal CSV helpers."""


def parse_row(line: str) -> list[str]:
    """Split one CSV line into its fields."""
    return line.split(",")
