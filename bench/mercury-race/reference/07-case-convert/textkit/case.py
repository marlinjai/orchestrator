import re


def camel_to_snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def snake_to_camel(name: str, upper: bool = False) -> str:
    parts = [p for p in name.split("_") if p]
    if not parts:
        return ""
    head = parts[0].capitalize() if upper else parts[0].lower()
    return head + "".join(p.capitalize() for p in parts[1:])
