# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Autonomous Claude Code orchestrator. Spawns a Worker (Claude Code SDK session) on a goal file, polls its transcript between iterations, and feeds each iteration's diff/state into a stateless Decision Proxy (LLM) that returns one of: `continue | replan | escalate | stop`. State is persisted to `~/.orchestrator/tasks/<task-id>/` (override with `ORCHESTRATOR_HOME`).

## Commands

Setup uses `uv` + editable install:

    uv venv && source .venv/bin/activate
    uv pip install -e ".[dev]"

Run / inspect:

    orchestrator start --goal <path> --project <path> --task-id <slug> --max-iterations 25 --max-hours 0.75
    orchestrator status --task-id <id>
    orchestrator stop   --task-id <id>      # touches kill-switch; halts at next iteration boundary
    orchestrator logs   --task-id <id> [-f]

Tests:

    pytest -v                       # full suite (asyncio_mode=auto, configured in pyproject)
    pytest tests/test_worker.py -v  # single module
    pytest tests/test_worker.py::test_name
    python scripts/smoke_sdk.py     # SDK + hook-isolation smoke test

## Architecture

The control loop lives in `orchestrator/orchestrator.py`. One iteration =

1. Worker (Claude Agent SDK session, configured in `worker.py`) runs against the goal file inside `--project`. The Worker reports progress by calling the custom MCP tool `update_state` from `tools.py` (kinds: `file_touched`, `commit`, `decision`, `open_thread`, ...). The Worker's `mcp_servers` and `allowed_tools` start from a fixed safe default (the `orchestrator-state` + `secrets-proxy` MCP servers and a default tool list). A goal file can ADD to both via optional frontmatter, `worker_mcp_servers` and `worker_allowed_tools` (parsed by `load_worker_extras`, merged in `build_worker_options`). These are pure unions: a goal can never drop a default server or tool. `worker_mcp_servers` names servers by key from `WORKER_MCP_REGISTRY` (a vetted allowlist in `worker.py`); a goal cannot inject an arbitrary stdio/env config, and an unknown key is dropped with a warning. Coolify is deliberately NOT in the registry: its tools can return secrets into the transcript, so a Worker needing Coolify uses the Coolify-via-proxy curl pattern through the `secrets-proxy` MCP instead. When you add a server to the registry, it must be non-secret-leaking.
2. After the Worker turn, the orchestrator parses the JSONL transcript (`transcript.py::extract_text`) and asks the Decision Proxy (`proxy.py`, persona at `personas/default.md`) for the next action. Proxy is stateless: each call is a fresh single-shot LLM with the persona + the iteration's state snapshot.
3. State is a pydantic model in `state.py` written atomically (tmp + rename) to `state.json`. `guardrails.py` enforces iteration cap, wall-clock cap, bash denylist, the kill-switch file, the optional per-run dollar cap, and the per-run cumulative token cap (`--max-tokens`, the rate-limit runaway guard now that billing is flat). `usage_guard.py` adds the fleet-wide layer: a `GLOBAL_STOP` panic file and a rolling 24h token budget (`ORCHESTRATOR_DAILY_TOKEN_CAP`) summed across all runs via a shared `usage-ledger.jsonl`. Both fleet guards are operator-owned and un-promptable. `stagnation.py` hard-stops a run whose structured progress (plan-step / decision / verify movement, never git churn) stalls for N iterations.
4. On a `stop`-candidate iteration, the in-loop verify gate (`verify.py`) runs the goal's `verify` command (frontmatter-declared, e.g. `pnpm test && pnpm build && tsc --noEmit && pnpm lint`) in the project worktree BEFORE accepting `completed`. Pass goes straight to `completed`; a failure is fed back to the Worker (evaluator-optimizer) for up to `verify_fix_cap` retries (default 2) then escalates; a denylisted command or a timeout escalates immediately. A goal with no `verify` command completes with a logged warning (no build verification). The gate is domain-agnostic: project-specific critics (e.g. a values-only schema round-trip) are appended to the goal's `verify` command (`... && pnpm verify:schema-roundtrip`), never built into the orchestrator. Before a pass is accepted, the cheap tamper tripwire (`tamper.py`) scans the changed test files against `baseline_ref`: a deleted test or a dropped assertion count downgrades the pass to `escalate` and records `state.tamper_paths` (a test merely edited is a log signal only). This is the cheap reward-hack tripwire, not the full held-out verifier (a later wave).

Key boundary: the Worker is the only thing that touches the project repo. The Proxy never executes code, only reads state. The orchestrator process owns state.json and the kill switch.

### Marlin Proxy (layered autonomy)

When the Decision Proxy returns `escalate`, the orchestrator (if `marlin_proxy.mode != off`) calls the Marlin Proxy (`marlin_proxy.py`) before interrupting Marlin. It is a second stateless single-shot LLM call using `personas/marlin.md`, returning a `MarlinDecision` (`auto_approve | auto_defer | escalate`) plus a category. Config (`config.py`, from `~/.config/orchestrator/config.toml` + per-task goal frontmatter) maps each category to `live | shadow | escalate`. `live` lets the proxy decide; `shadow` decides-but-still-escalates (logging the would-be choice for later agreement review); `escalate` always interrupts. `irreversible_ops` (prod, secrets, DNS) is hard-wired to escalate and cannot be relaxed by config or per-task frontmatter. Every decision is appended to an append-only JSONL ledger (`ledger.py`) plus a human-readable `notes.md`; `state.autonomy_stats` tracks streaks and autonomous runtime. Fast paths: a kill-switch file and context-saturation both force escalate before any token spend. Malformed persona output or a timeout also fail safe to escalate, never to a silent auto-approve. Review via `orchestrator marlin-proxy review`. Defaults to `mode=off`; nothing auto-decides until explicitly enabled.

### SDK gotchas (load-bearing, learned via dogfood)

- `CLAUDE_DISABLE_HOOKS=1` is a phantom env var. Hook isolation is achieved via `ClaudeAgentOptions(setting_sources=[])` in `worker.py`. Do not regress this: SessionStart token bloat will silently consume the Worker's context. Note `setting_sources=[]` is ONLY hook isolation; it does not gate MCP servers, which are passed explicitly via `mcp_servers`. Per-goal MCP servers are added through `WORKER_MCP_REGISTRY` + frontmatter, not by touching `setting_sources`.
- Custom MCP tool schemas: dict-shorthand `@tool` makes ALL fields required. For partial-arg tools (like `update_state`), declare explicit JSON-schema with `required: [...]`. See `tools.py`.
- Real Claude Code transcripts nest role inside `msg["message"]["role"]`, not top-level. `transcript.py::_extract_text` handles this; don't simplify.

### Worker system prompt: shared-index discipline

`WORKER_SYSTEM_PROMPT` in `worker.py` contains a "shared index/status files" section. When parallel Workers were dispatched against the same repo, each invented a different STATUS.md format and forced manual merge cleanup. Rule: touch only your row, preserve the existing column format exactly, never add columns or suffixes, spec frontmatter is canonical. Keep this section intact when editing the prompt.

## Operational patterns

Parallel batch: one worktree per task (`git worktree add ../<repo>-orch-<slug> orchestrator/<slug>`), one goal file per task at `goals/<task-id>.md`, launch each detached with `nohup ... &`. Each Worker gets its own checkout, branch, and state dir. Cherry-pick branches back to main; gate on `pnpm test && pnpm build` before any push. Pro plan handled 3 concurrent Worker + Proxy sessions cleanly on single-iteration tasks; longer multi-iteration runs are untested under load.

State directory layout per task:

    ~/.orchestrator/tasks/<task-id>/
      state.json         # pydantic-validated, atomic writes
      run.log            # tee'd stdout/stderr from the Worker session
      STOP                # presence = halt at next iteration boundary (written by `orchestrator stop`)

## Operator skill (bundled)

The Claude Code operator playbook lives in this repo at `skills/autonomous-orchestration/SKILL.md`, versioned alongside the code it documents. The `marlinjai/bootstrap` `orchestrator-cli` module installs the CLI and symlinks this skill into `~/.claude/skills/`, so the skill never drifts from the CLI version. When you change CLI behavior (new flags, state fields, the Marlin Proxy), update the skill in the same PR.

## Style

Repo-level: no em-dashes / en-dashes in any output (commit messages included). Conventional-commit messages. Single commit per Worker-completed spec on its branch.
