"""Minimal YAML-frontmatter parser for goal files.

The project intentionally has no YAML dependency. Goal-file frontmatter uses a
small, predictable subset: top-level scalars, one level of nested mapping, and
inline `[a, b]` lists. This parser handles exactly that subset and ignores the
rest, so it is safe to run on any goal file.
"""


def _strip_value(raw: str) -> str:
    value = raw.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_inline_list(raw: str) -> list[str]:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    return [_strip_value(part) for part in inner.split(",") if part.strip()]


def parse_frontmatter(text: str) -> dict:
    """Extract the leading `---` frontmatter block as a dict. Returns {} when
    there is no frontmatter. Supports scalars, inline lists, and one level of
    nested mappings (2-space indented).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    block: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        block.append(line)

    result: dict = {}
    current_map_key: str | None = None

    for line in block:
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indented = line[0] in (" ", "\t")
        stripped = line.strip()
        if ":" not in stripped:
            current_map_key = None
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if indented and current_map_key is not None:
            nested = result.setdefault(current_map_key, {})
            if isinstance(nested, dict):
                nested[key] = _strip_value(value)
            continue

        # top-level key
        current_map_key = None
        if value == "":
            current_map_key = key
            result.setdefault(key, {})
        elif value.startswith("[") and value.endswith("]"):
            result[key] = _parse_inline_list(value)
        else:
            result[key] = _strip_value(value)

    # Drop empty nested maps that never got children (they were really blank scalars).
    for k in list(result.keys()):
        if result[k] == {}:
            result[k] = ""
    return result
