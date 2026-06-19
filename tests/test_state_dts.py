"""Anti-drift guard for the generated TypeScript state contract.

types/state.d.ts is codegen'd from the Pydantic State model by
scripts/gen_state_dts.py. A consumer (a future Kanban board) reads state.json
against that contract, so the committed .d.ts must always match the live model.
This test regenerates into memory and asserts byte-equality with the committed
file: it fails the moment State changes without the contract being regenerated.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR_PATH = REPO_ROOT / "scripts" / "gen_state_dts.py"
COMMITTED_DTS = REPO_ROOT / "types" / "state.d.ts"


def _load_generator():
    """Import scripts/gen_state_dts.py as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("gen_state_dts", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_dts_exists():
    assert COMMITTED_DTS.exists(), (
        f"{COMMITTED_DTS} is missing. Run: uv run python scripts/gen_state_dts.py"
    )


def test_state_dts_matches_model():
    """The committed .d.ts must byte-match a fresh regenerate from the model.

    If this fails, the Pydantic State model changed but types/state.d.ts was not
    regenerated. Fix: run `uv run python scripts/gen_state_dts.py` and commit the
    updated types/state.d.ts.
    """
    gen = _load_generator()
    regenerated = gen.generate()
    committed = COMMITTED_DTS.read_text()
    assert regenerated == committed, (
        "types/state.d.ts is out of sync with the Pydantic State model.\n"
        "Regenerate it with: uv run python scripts/gen_state_dts.py"
    )


def test_generator_check_mode_passes():
    """`gen_state_dts.py --check` returns 0 when the committed file is current."""
    gen = _load_generator()
    assert gen.main(["--check"]) == 0


def test_contract_covers_full_surface():
    """Every nested model and Literal alias is present in the contract.

    A coverage assertion so a silently-dropped interface (an emitter regression
    that still byte-matches a stale file) is caught independently of the diff.
    """
    text = COMMITTED_DTS.read_text()
    expected_interfaces = [
        "AutonomyStats",
        "CommitEntry",
        "Decision",
        "FileTouched",
        "Handover",
        "HeldOutRecord",
        "IterationUsage",
        "PlanStep",
        "VerifyRecord",
        "State",
    ]
    for name in expected_interfaces:
        assert f"export interface {name} {{" in text, f"missing interface {name}"

    expected_aliases = ["PlanStatus", "TaskStatus", "DecidedBy", "VerifyStatus"]
    for name in expected_aliases:
        assert f"export type {name} =" in text, f"missing literal alias {name}"


def test_every_state_field_is_emitted():
    """Each State field name appears in the emitted State interface."""
    from orchestrator.state import State

    text = COMMITTED_DTS.read_text()
    state_block = text.split("export interface State {", 1)[1]
    for field_name in State.model_fields:
        assert f"{field_name}" in state_block, (
            f"State field {field_name!r} is not present in the emitted contract"
        )


def test_generator_writes_idempotently(tmp_path: Path, monkeypatch):
    """Writing the contract then regenerating is a no-op (deterministic output)."""
    gen = _load_generator()
    first = gen.generate()
    second = gen.generate()
    assert first == second


def test_drift_is_detected_by_check(monkeypatch):
    """A simulated model change makes --check fail (the guard genuinely bites).

    We monkeypatch the generator so it emits a phantom extra field, then assert
    --check returns non-zero against the unchanged committed file. This proves
    the guard would catch a real model change that forgot to regenerate, without
    mutating any file on disk.
    """
    gen = _load_generator()
    real_generate = gen.generate

    def drifted_generate():
        return real_generate().replace(
            "export interface State {",
            "export interface State {\n  phantom_field?: string;",
            1,
        )

    monkeypatch.setattr(gen, "generate", drifted_generate)
    assert gen.main(["--check"]) == 1
