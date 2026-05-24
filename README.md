# orchestrator

Autonomous Claude Code orchestrator. Spawns a Worker (Claude Code SDK session) on a goal file, polls its transcript, and feeds each iteration to a stateless Decision Proxy that returns `continue | replan | escalate | stop`. Design spec at `~/software-dev/knowledge-base/docs/superpowers/specs/2026-05-08-autonomous-claude-orchestrator-design.md`.

## Install

Two paths:

**As a global CLI** (recommended for cross-project use):

    uv tool install git+https://github.com/marlinjai/orchestrator
    # or, for local development:
    cd ~/software-dev/orchestrator && uv tool install --editable .

After install, the `orchestrator` binary is on PATH everywhere.

**For repo development** (running tests, editing source):

    uv venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"

## First-run smoke (5 minutes)

Verifies the full stack: Worker spawns on subscription auth, makes a real commit, reconciliation detects it, telemetry captures token usage.

    # 1. Create a tiny scratch repo
    mkdir -p /tmp/orch-smoke && cd /tmp/orch-smoke
    git init -q && git config user.email t@example.com && git config user.name T
    echo "initial" > README.md && git add . && git commit -q -m "init"

    # 2. Write a one-iteration goal
    cat > /tmp/orch-smoke-goal.md <<'EOF'
    # Goal
    Append `## Scratch` to README.md, commit with message `docs: add scratch heading`, then declare done.
    EOF

    # 3. Launch (uses your Claude Code login subscription; no API spend)
    cd ~/software-dev/orchestrator
    orchestrator start --goal /tmp/orch-smoke-goal.md --project /tmp/orch-smoke \
      --task-id smoke --max-iterations 3 --max-hours 0.1

    # 4. Inspect
    orchestrator status --task-id smoke

Expected: `status: completed`, `commits: 1 (proxy=1, system=0)` (or `proxy=0 system=1` if the Worker didn't self-report), `tokens: in=... out=... cache_r=...` with non-zero numbers.

## Run

    orchestrator start \
      --goal goals/<task-id>.md \
      --project ~/path/to/your/project \
      --task-id <slug> \
      --max-iterations 25 \
      --max-hours 0.75

Goal files live in `goals/`. Start from `goals/_template.md`.

CLI commands:

- `orchestrator start --goal <path> --project <path>`: launch a new autonomous run.
- `orchestrator status --task-id <id>`: print state.json fields as a table.
- `orchestrator stop --task-id <id>`: touch the kill-switch file. Orchestrator halts at the next iteration boundary.
- `orchestrator logs --task-id <id> [-f]`: print or tail `run.log` for a task.

State lives at `~/.orchestrator/tasks/<task-id>/` (override with `ORCHESTRATOR_HOME`).

## Secrets and auth (read this before wrapping the launcher)

The Worker uses your Claude Code login session by default (`~/.config/claude/.credentials.json`), not the Anthropic API. This means: zero per-token API spend on runs.

The Claude Agent SDK auth precedence is:

1. `ANTHROPIC_API_KEY` in env → direct API billing on that key
2. `CLAUDE_CODE_OAUTH_TOKEN` → subscription
3. `~/.config/claude/.credentials.json` (your `claude login` session) → **subscription** (the default)

If the orchestrator process ever sees `ANTHROPIC_API_KEY` in its environment, the SDK silently switches from your subscription to API billing on that key. This was an actual production failure on 2026-05-24 when a launcher was wrapped in `infisical run --env=dev --path=/ --` to inject the key for a Next.js app's runtime use: the orchestrator's *own* Worker switched to API billing and aborted with "Credit balance is too low".

**The orchestrator now scrubs `ANTHROPIC_API_KEY` from its env at the SDK-spawn boundary** (`orchestrator/worker.py::_scrub_anthropic_api_key`). Subscription wins regardless of how the launcher was invoked.

Practical implications:

- **It is safe** to wrap the launcher in `infisical run` for unrelated secrets. The scrub keeps the Worker on subscription.
- The Worker only needs to write code that *references* `process.env.ANTHROPIC_API_KEY` at the *target app's* runtime. The key only needs to exist later (e.g. when you run `pnpm dev` in the target repo), not at orchestrator-spawn time.
- Never set `ANTHROPIC_API_KEY` in shell rc files thinking it'll "help" the orchestrator. It'll be scrubbed anyway, but the intent is wrong.

## state.json reference (v0.2+)

| Field | Meaning |
|---|---|
| `task_id` | The slug passed via `--task-id` |
| `status` | `running` / `completed` / `escalated` / `stopped` / `failed` |
| `iteration` | Worker turns completed |
| `baseline_ref` | git HEAD of `--project` at orchestrator start; reconciliation anchor |
| `commits[]` | `{sha, message, decided_by, recorded_at}`. `decided_by=proxy` means the Worker self-reported via `update_state`; `decided_by=system` means the orchestrator reconciled it from `git log baseline..HEAD`. |
| `files_touched[]` | `{path, decided_by, recorded_at}`. Same provenance model. Includes uncommitted edits via `git diff` + untracked. |
| `usage[]` | Per-iteration `{iteration, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model, worker_ms, proxy_ms}`. Use cumulative sums to estimate burn rate. |
| `decisions[]` | Worker-reported decisions (currently underused; see Proxy feedback in v2 backlog) |
| `open_threads[]` | Deferred follow-ups the Worker logged |
| `exit_reason` | Free-text terminal explanation |

## Troubleshooting

**"Credit balance is too low" on iteration 1 with no Worker output.**
The `ANTHROPIC_API_KEY` scrub regressed, or the SDK is reading the key from somewhere outside `os.environ` (rare). Check `worker.py::_scrub_anthropic_api_key` is still being called in `build_worker_options`. Verify with `pytest tests/test_worker.py::test_worker_options_scrubs_anthropic_api_key`.

**Worker completed but `commits: 0` despite real commits on the branch.**
Worker didn't call `update_state(kind="commit")`. The reconciler should have caught it: check `state.commits` for entries with `decided_by="system"`. If those are missing, `state.baseline_ref` was None (project isn't a git repo, or `git rev-parse HEAD` failed at start). The reconciler is a no-op when baseline_ref is None.

**Run hangs forever, no iteration progress.**
Touch the kill switch: `orchestrator stop --task-id <id>`. It creates `~/.orchestrator/tasks/<id>/STOP`; the orchestrator halts at the next iteration boundary. If a Worker turn itself hangs (rare), `kill -9` the orchestrator PID.

**State file fails to load with validation error after upgrading from v0.1.x.**
v0.2 broke the state schema (commits and files_touched moved from `list[str]` to objects with provenance). No migration is provided; archive the old `state.json` and start fresh. Per the dev-phase no-backcompat rule.

**Same commit shows up twice in `commits[]`.**
Should not happen as of v0.2 (`reconcile.py::_sha_already_known` prefix-matches short vs full shas). If it does, file an issue with the offending state.json.

**Parallel Workers conflict on STATUS.md / ROADMAP.md / shared index files.**
The Worker system prompt has shared-index edit discipline (commit `e2bb6ef`). If you still see merge conflicts on those files, check whether your goal file is overriding that section. Don't tell Workers to "update STATUS.md" with custom format guidance; let the prompt handle it.

**Token usage grows linearly each iteration with no `cache_read_tokens`.**
Prompt caching isn't hitting. Either the system prompt is changing between turns (rare; the orchestrator doesn't modify it), or the SDK version is too old. Update `claude-agent-sdk`.

## For Claude Code sessions

The `autonomous-orchestration` skill at `~/.claude/skills/autonomous-orchestration/SKILL.md` auto-triggers when you ask Claude Code to "run autonomously", "dispatch", "kick off in the background", "launch a batch", or anything goal-file-driven. The skill body covers the parallel-batch pattern, monitoring, the secrets-and-auth caveat, and state.json fields. Source-of-truth lives in `~/software-dev/dotfiles/claude/skills/autonomous-orchestration/SKILL.md`; the install.sh symlinks it on every machine.

Open this README for the operator's view; let the skill brief Claude on the dispatch view.

## Find the open work

[ROADMAP.md](ROADMAP.md) tracks shipped versions, queued v2 themes (env-mode contract, stagnation-streak loop detection, Proxy feedback, handover scaffold, batch subcommand), open follow-ups, and known unknowns.

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

## v0.1.x parallel-batch field notes (2026-05-10)

Four wave-1 specs landed in the framer-clone repo across two sessions:

1. Single sequential run on a worktree: `static-html-data-component-id-fix`, 1 iteration, ~4 min.
2. Parallel triple in three worktrees: `data-bindings-binding-shape`, `multiplayer-yjs-doc-shape`, `data-bindings-data-source-provider`. Each completed in 1 iteration, ~5 min, dispatched concurrently.

All four runs: zero escalations, zero retries, zero failed iterations.

**What the parallel pattern proved:**
- Worktree isolation works. Each Worker had its own checkout, its own branch, its own state directory. Cherry-picking the resulting branches back to main was clean.
- Pro subscription handled three concurrent Worker sessions plus three concurrent Proxy decisions without rate-limit warnings (one-iteration tasks, low token volume).
- The orchestrator binary handled the `nohup ... &` detach pattern cleanly. Each task survived past its launcher's shell.

**What broke (and got fixed):**
- **Shared-index file conflict.** Three parallel Workers each invented a different STATUS.md format when editing it concurrently (annotation suffix, emoji suffix, Status column at end, Status column mid-table). Forced manual merge cleanup. Fix: added "Edit discipline for shared index/status files" to WORKER_SYSTEM_PROMPT in `worker.py`. New rule: touch only your row, preserve format exactly, never add columns or reformat tables, spec frontmatter is canonical, mirror neighbor rows.

**Operational recipe (validated):**

```bash
# 1. Set up a worktree per spec
cd <project-repo>
git worktree add ../<repo>-orch-<spec-slug> orchestrator/<spec-slug>

# 2. Write per-task goal file at goals/<task-id>.md

# 3. Launch detached (repeat per task in parallel)
cd ~/software-dev/orchestrator
source .venv/bin/activate
nohup orchestrator start \
  --goal goals/<task-id>.md \
  --project <worktree-path> \
  --task-id <task-id> \
  --max-iterations 30 \
  --max-hours 1.0 \
  > /tmp/orch-<task-id>.log 2>&1 &

# 4. Monitor via state.json polling until terminal status
# 5. Cherry-pick each branch onto main, run gates, push
# 6. git worktree remove each path
```

**Open issues for v2:**
- Loop detection is still untested in the wild (all completions have been single-iteration).
- Context handover is still untested (no run has approached context budget).
- Token-usage tracking still missing.
- No tool for "did the Worker actually call update_state(decision) often enough to feed the Proxy good context?" The feedback loop is one-sided.

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
