# orchestrator

Autonomous Claude Code orchestrator. See design spec at
`~/software-dev/knowledge-base/docs/superpowers/specs/2026-05-08-autonomous-claude-orchestrator-design.md`.

## Install

    uv venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"

## Run

    orchestrator start --goal goals/write-orchestrator-plan.md
