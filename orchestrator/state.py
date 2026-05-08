import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError


PlanStatus = Literal["pending", "in_progress", "completed", "skipped"]
TaskStatus = Literal["running", "stopped", "completed", "escalated", "failed"]
DecidedBy = Literal["proxy", "user", "system"]


class PlanStep(BaseModel):
    id: int
    step: str
    status: PlanStatus = "pending"


class Decision(BaseModel):
    turn: int
    question: str
    answer: str
    reasoning: str
    decided_by: DecidedBy


class Handover(BaseModel):
    at_turn: int
    reason: str
    doc: str


class State(BaseModel):
    task_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    goal: str
    plan: list[PlanStep] = []
    current_step_id: int | None = None
    decisions: list[Decision] = []
    files_touched: list[str] = []
    commits: list[str] = []
    open_threads: list[str] = []
    iteration: int = 0
    max_iterations: int = 50
    handovers: list[Handover] = []
    status: TaskStatus = "running"
    exit_reason: str | None = None


def load_state(path: Path) -> State:
    if not path.exists():
        raise FileNotFoundError(f"state file not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"state file corrupt: {path}: {e}") from e
    try:
        return State.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"state file schema mismatch: {path}: {e}") from e


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = state.model_dump_json(indent=2)
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(serialized)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
