"""Generate types/state.d.ts from the Pydantic State model.

WHY: a future Kanban board reads state.json directly. Hand-written TypeScript
would silently drift the moment the Python model changes. This emitter walks
State.model_json_schema() and produces a deterministic .d.ts, so the contract
is regenerated (and diff-tested) from the single source of truth, never typed
by hand.

This is a self-contained, pure-Python emitter: no node toolchain, no
pydantic2ts, no json-schema-to-typescript. It depends only on pydantic (already
a runtime dependency) plus the standard library.

Usage:
    uv run python scripts/gen_state_dts.py            # write types/state.d.ts
    uv run python scripts/gen_state_dts.py --check     # regenerate + diff (CI)

--check exits non-zero (and prints a diff) when the committed file is stale,
so `uv run pytest` fails the moment the model changes without a regenerate.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from orchestrator.state import State

# Repo-root-relative output path. The script lives in scripts/, so the repo
# root is one level up, regardless of the caller's cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "types" / "state.d.ts"

GENERATOR_REL = "scripts/gen_state_dts.py"
SOURCE_REL = "orchestrator/state.py (State.model_json_schema())"

# The four Literal aliases from orchestrator/state.py. Pydantic inlines a
# Literal as a bare `enum` array (no $ref, no title), so the alias name is lost
# in the schema. We recover the names by matching the exact frozen value-set,
# which keeps the emitted unions readable (`PlanStatus`) instead of repeating
# the raw union at every field. The value tuples MUST stay in declaration order
# so the emitted union is stable and matches state.py.
LITERAL_ALIASES: dict[str, tuple[str, ...]] = {
    "PlanStatus": ("pending", "in_progress", "completed", "skipped"),
    "TaskStatus": ("running", "stopped", "completed", "escalated", "failed"),
    "DecidedBy": ("proxy", "user", "system"),
    "VerifyStatus": ("pass", "fail", "misconfigured"),
}
# Reverse lookup: frozenset of values -> alias name.
_ALIAS_BY_VALUES: dict[frozenset[str], str] = {
    frozenset(values): name for name, values in LITERAL_ALIASES.items()
}

HEADER = (
    "// GENERATED FILE: DO NOT EDIT BY HAND.\n"
    f"// Source: {SOURCE_REL}.\n"
    f"// Regenerate with: uv run python {GENERATOR_REL}\n"
    "//\n"
    "// This typed contract mirrors the orchestrator State model so a consumer\n"
    "// (e.g. a Kanban board reading state.json) cannot silently drift from the\n"
    "// Python source. A drift test (tests/test_state_dts.py) fails the suite if\n"
    "// this file is stale.\n"
)


class GeneratorError(RuntimeError):
    """Raised when the schema contains a shape the emitter does not handle.

    Failing loud beats emitting a silently-wrong contract: a new field type the
    emitter cannot map is a bug to fix in the emitter, not something to paper
    over with `any`.
    """


def _quote(value: str) -> str:
    """A double-quoted TS string literal for an enum member."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _union_of_literals(values: list[str]) -> str:
    return " | ".join(_quote(v) for v in values)


def _scalar_type(schema: dict) -> str:
    """Map a JSON-schema scalar `type` to its TypeScript scalar."""
    json_type = schema.get("type")
    if json_type == "string":
        # ISO datetime fields carry format=date-time; they serialize as strings.
        return "string"
    if json_type in ("integer", "number"):
        return "number"
    if json_type == "boolean":
        return "boolean"
    if json_type == "null":
        return "null"
    raise GeneratorError(f"unhandled scalar schema: {schema!r}")


def _resolve_ref(schema: dict) -> str:
    """Resolve a `$ref` to the referenced interface name."""
    ref = schema["$ref"]
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        raise GeneratorError(f"unhandled $ref shape: {ref!r}")
    return ref[len(prefix) :]


def ts_type_for(schema: dict) -> str:
    """Render the TypeScript type for one property schema.

    Handles: $ref (nested model), enum (Literal union, named when known),
    arrays (T[]), anyOf nullable unions, and scalars. Anything else is a
    GeneratorError so an unmapped shape is caught in CI, never emitted as `any`.
    """
    if "$ref" in schema:
        return _resolve_ref(schema)

    if "enum" in schema:
        values = list(schema["enum"])
        alias = _ALIAS_BY_VALUES.get(frozenset(values))
        if alias is not None:
            return alias
        return _union_of_literals(values)

    if "anyOf" in schema:
        parts = [ts_type_for(sub) for sub in schema["anyOf"]]
        # Deduplicate while preserving order (a "null" can appear once).
        seen: dict[str, None] = {}
        for part in parts:
            seen.setdefault(part, None)
        return " | ".join(seen)

    json_type = schema.get("type")
    if json_type == "array":
        items = schema.get("items", {})
        inner = ts_type_for(items)
        # Parenthesize union element types so `(A | B)[]` parses as an array of
        # the union, not a union with a trailing array.
        if " | " in inner:
            inner = f"({inner})"
        return f"{inner}[]"

    return _scalar_type(schema)


def _is_optional(prop_name: str, prop_schema: dict, required: set[str]) -> bool:
    """A property is optional (gets `?`) when it is not in `required`.

    Pydantic puts a field in `required` only when it has no default and is not
    nullable. Every field with a default (including default_factory models like
    autonomy_stats) or a `| None` type is therefore absent from `required`, so
    this single check covers both the "has a default" and "is nullable" cases.
    """
    return prop_name not in required


def emit_interface(name: str, obj_schema: dict) -> str:
    """Emit one `export interface` block for an object model."""
    required = set(obj_schema.get("required", []))
    props: dict = obj_schema.get("properties", {})
    lines = [f"export interface {name} {{"]
    # Preserve the property order from the schema (Python 3.7+ dicts and
    # pydantic both preserve declaration order), so output is deterministic.
    for prop_name, prop_schema in props.items():
        optional = "?" if _is_optional(prop_name, prop_schema, required) else ""
        ts_type = ts_type_for(prop_schema)
        lines.append(f"  {prop_name}{optional}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def emit_literal_alias(name: str, values: tuple[str, ...]) -> str:
    return f"export type {name} = {_union_of_literals(list(values))};"


def generate() -> str:
    """Produce the full .d.ts text from State.model_json_schema()."""
    schema = State.model_json_schema()
    defs: dict = schema.get("$defs", {})

    blocks: list[str] = [HEADER.rstrip("\n")]

    # 1. Literal aliases first, in declaration order (state.py order), so the
    #    interfaces below can reference them by name.
    alias_block = "\n".join(
        emit_literal_alias(name, values) for name, values in LITERAL_ALIASES.items()
    )
    blocks.append(alias_block)

    # 2. Nested-model interfaces, sorted by name for a stable, deterministic
    #    layout (the $defs dict order is alphabetical already, but we sort
    #    explicitly so output never depends on pydantic's internal ordering).
    for def_name in sorted(defs):
        def_schema = defs[def_name]
        if def_schema.get("type") != "object":
            raise GeneratorError(
                f"$def {def_name!r} is not an object schema; emitter only knows "
                "how to render object models as interfaces"
            )
        blocks.append(emit_interface(def_name, def_schema))

    # 3. The top-level State interface last (it references everything above).
    blocks.append(emit_interface("State", schema))

    # Single trailing newline; blocks separated by one blank line.
    return "\n\n".join(blocks) + "\n"


def _read_existing() -> str | None:
    if OUTPUT_PATH.exists():
        return OUTPUT_PATH.read_text()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate and diff against the committed file; non-zero exit on mismatch",
    )
    args = parser.parse_args(argv)

    generated = generate()

    if args.check:
        existing = _read_existing()
        if existing == generated:
            return 0
        existing_lines = (existing or "").splitlines(keepends=True)
        diff = difflib.unified_diff(
            existing_lines,
            generated.splitlines(keepends=True),
            fromfile=f"{OUTPUT_PATH} (committed)",
            tofile=f"{OUTPUT_PATH} (regenerated)",
        )
        sys.stderr.write("".join(diff))
        sys.stderr.write(
            f"\ntypes/state.d.ts is stale. Run: uv run python {GENERATOR_REL}\n"
        )
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(generated)
    sys.stdout.write(f"wrote {OUTPUT_PATH}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
