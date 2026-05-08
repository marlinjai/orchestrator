# orchestrator

Autonomous Claude Code orchestrator. See design spec at
`~/software-dev/knowledge-base/docs/superpowers/specs/2026-05-08-autonomous-claude-orchestrator-design.md`.

## Install

    uv venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"

## Run

    orchestrator start \
      --goal goals/write-orchestrator-plan.md \
      --project ~/path/to/your/project \
      --task-id <slug> \
      --max-iterations 25 \
      --max-hours 0.75

CLI commands:

- `orchestrator start --goal <path> --project <path>`: launch a new autonomous run.
- `orchestrator status --task-id <id>`: print state.json fields as a table.
- `orchestrator stop --task-id <id>`: touch the kill-switch file. Orchestrator halts at the next iteration boundary.
- `orchestrator logs --task-id <id> [-f]`: print or tail `run.log` for a task.

State lives at `~/.orchestrator/tasks/<task-id>/` (override with `ORCHESTRATOR_HOME`).

## v0.1.0 dogfood field report (2026-05-09)

First end-to-end run: the orchestrator wrote its own v2 plan as a dogfood task. Notes for v2 work:

**What worked:**
- One iteration, ~9 minutes wall clock, completed cleanly.
- Worker called `update_state` for `file_touched` and `commit` correctly. MCP tool wiring is solid.
- `_extract_text` handled the SDK message shape on the first try (no adaptation needed).
- Proxy correctly identified the Worker's "Task complete" message and emitted `stop`.
- Hook isolation via `setting_sources=[]` worked (no SessionStart token bloat in the Worker).
- `run.log` tee captured the full session; `orchestrator logs` is usable.

**What surprised:**
- A 3048-line plan in one Worker turn. Single-iteration tasks happen when the goal is well-scoped and Worker has the context budget. Don't assume multi-turn always.
- The Worker did not call `update_state(kind="decision")` for its own internal decisions, only for files and commits. Decisions list ended up empty. Acceptable for v1 but the persona could nudge the Worker to record reasoning explicitly if we want richer state for the Proxy on longer runs.
- Pro plan rate limits were not hit on a single-Worker-turn run. A longer multi-iteration run is a real risk.

**SDK gotchas confirmed:**
- `CLAUDE_DISABLE_HOOKS=1` is a phantom env var, not honored anywhere. Use `ClaudeAgentOptions(setting_sources=[])`.
- Dict-shorthand `@tool` schema makes ALL fields required. Use explicit JSON-schema with `required: [...]` for partial-arg tools.
- Real Claude Code transcripts nest role inside `msg["message"]["role"]`, not at top level.

**v2 priority signals (from this run):**
- Token-usage tracking is needed before we ship any task that runs more than a few iterations.
- Handover is genuinely deferred until we see a context-exhausting task in the wild.
- Loop detection is a safety net we have not yet tripped, but the iteration cap caught nothing because the Worker self-completed.

## Repo layout

    orchestrator/
    ├── orchestrator/        # package
    │   ├── main.py          # CLI (typer)
    │   ├── orchestrator.py  # main loop
    │   ├── worker.py        # Worker SDK options
    │   ├── proxy.py         # stateless Decision Proxy
    │   ├── state.py         # pydantic state.json + atomic I/O
    │   ├── guardrails.py    # bash denylist + caps + kill switch
    │   ├── transcript.py    # JSONL parser + extract_text
    │   └── tools.py         # update_state custom MCP tool
    ├── personas/
    │   └── default.md       # decision proxy persona
    ├── goals/
    │   └── write-orchestrator-plan.md  # first dogfood goal
    ├── scripts/
    │   └── smoke_sdk.py     # SDK + hook-isolation smoke test
    └── tests/               # 89 tests across 8 modules

## Development

    pytest -v                # full suite
    pytest tests/test_X.py   # one module
    python scripts/smoke_sdk.py  # SDK isolation smoke test
