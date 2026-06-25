"""Generate the typed TS contracts (types/state.d.ts + types/events.d.ts) from
the Pydantic models.

WHY: a future Kanban board reads state.json directly and consumes the
normalized event stream (orchestrator/events.py). Hand-written TypeScript would
silently drift the moment a Python model changes. This emitter walks
`State.model_json_schema()` and `Event.model_json_schema()` and produces
deterministic .d.ts files, so the contracts are regenerated (and diff-tested)
from the single source of truth, never typed by hand.

This is a self-contained, pure-Python emitter: no node toolchain, no
pydantic2ts, no json-schema-to-typescript. It depends only on pydantic (already
a runtime dependency) plus the standard library.

Usage:
    uv run python scripts/gen_state_dts.py            # write both contracts
    uv run python scripts/gen_state_dts.py --check     # regenerate + diff (CI)

--check exits non-zero (and prints a diff) when a committed file is stale, so
`uv run pytest` fails the moment a model changes without a regenerate.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from orchestrator.events import EVENT_TYPES, Event
from orchestrator.state import State

# Repo-root-relative output paths. The script lives in scripts/, so the repo
# root is one level up, regardless of the caller's cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "types" / "state.d.ts"
EVENTS_OUTPUT_PATH = REPO_ROOT / "types" / "events.d.ts"

GENERATOR_REL = "scripts/gen_state_dts.py"
SOURCE_REL = "orchestrator/state.py (State.model_json_schema())"
EVENTS_SOURCE_REL = "orchestrator/events.py (Event.model_json_schema())"

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
# The events contract's one Literal alias, sourced straight from events.py so
# an EventType change flows into both the emitted `EventType` alias line and the
# `Event.type` field naming (and thus reddens the freshness test).
EVENT_LITERAL_ALIASES: dict[str, tuple[str, ...]] = {
    "EventType": tuple(EVENT_TYPES),
}
# Reverse lookup: frozenset of values -> alias name. Spans both contracts so
# `ts_type_for` can recover a named union for any known Literal (the State
# literals never match EventType's value-set, so this is collision-free).
_ALIAS_BY_VALUES: dict[frozenset[str], str] = {
    frozenset(values): name
    for name, values in {**LITERAL_ALIASES, **EVENT_LITERAL_ALIASES}.items()
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

EVENTS_HEADER = (
    "// GENERATED FILE: DO NOT EDIT BY HAND.\n"
    f"// Source: {EVENTS_SOURCE_REL}.\n"
    f"// Regenerate with: uv run python {GENERATOR_REL}\n"
    "//\n"
    "// The normalized event-stream contract a Kanban board reads: the typed\n"
    "// projection over State (orchestrator/events.py::project_events). A drift\n"
    "// test (tests/test_state_dts.py) fails the suite if this file is stale.\n"
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

    if json_type == "object":
        return _object_type(schema)

    return _scalar_type(schema)


def _object_type(schema: dict) -> str:
    """Map a free-form dict field (e.g. Event.data) to a TS index signature.

    Pydantic renders an untyped `dict` as `{"type": "object"}` with no
    `properties` (and `additionalProperties: true`). A typed `dict[str, T]`
    carries `additionalProperties` as the value schema; map that when present,
    else fall back to `unknown`. An inline object WITH `properties` is a shape
    the emitter does not model (nested models arrive via `$ref`), so it fails
    loud rather than emitting a silently-wrong type.
    """
    if "properties" in schema:
        raise GeneratorError(
            f"inline object with properties is not supported: {schema!r}"
        )
    additional = schema.get("additionalProperties")
    value_type = ts_type_for(additional) if isinstance(additional, dict) else "unknown"
    return f"{{ [key: string]: {value_type} }}"


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


def generate_events() -> str:
    """Produce types/events.d.ts from Event.model_json_schema().

    The Event model is flat (no nested $defs): a single `EventType` Literal
    alias plus the `Event` interface (its `data` dict becomes an index
    signature, its `type` field resolves to `EventType`).
    """
    schema = Event.model_json_schema()
    blocks: list[str] = [EVENTS_HEADER.rstrip("\n")]
    blocks.append(emit_literal_alias("EventType", EVENT_LITERAL_ALIASES["EventType"]))
    blocks.append(emit_interface("Event", schema))
    return "\n\n".join(blocks) + "\n"


# Each contract: (output path, generator NAME, human label). The generator is
# stored by NAME and resolved from module globals at call time so the drift
# tests can monkeypatch `generate` / `generate_events` and have main() honor it.
_CONTRACTS = (
    (OUTPUT_PATH, "generate", "types/state.d.ts"),
    (EVENTS_OUTPUT_PATH, "generate_events", "types/events.d.ts"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate and diff against the committed files; non-zero exit on mismatch",
    )
    args = parser.parse_args(argv)

    if args.check:
        stale = False
        for path, gen_name, label in _CONTRACTS:
            generated = globals()[gen_name]()
            existing = path.read_text() if path.exists() else None
            if existing == generated:
                continue
            stale = True
            diff = difflib.unified_diff(
                (existing or "").splitlines(keepends=True),
                generated.splitlines(keepends=True),
                fromfile=f"{path} (committed)",
                tofile=f"{path} (regenerated)",
            )
            sys.stderr.write("".join(diff))
            sys.stderr.write(
                f"\n{label} is stale. Run: uv run python {GENERATOR_REL}\n"
            )
        return 1 if stale else 0

    for path, gen_name, label in _CONTRACTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(globals()[gen_name]())
        sys.stdout.write(f"wrote {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
