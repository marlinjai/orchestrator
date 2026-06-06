---
type: plan
status: completed
title: "Context handover: Layer 3 (git-anchored) implementation"
summary: "Closes the gap between the designed handover scaffold and a real Layer 3 implementation. Adds a `handover` Proxy action, a git-anchored HANDOVER.md document authored by the Worker, and fresh-session spawning in the orchestrator loop. Trigger at 50-60% of context window, not 90%. Two phases: Phase A (manual trigger + anchored doc) lands immediately; Phase B (automatic threshold trigger) follows."
date: 2026-06-06
tags: [orchestrator, context-handover, layer3, marlin-proxy, worker, fresh-session]
projects: [orchestrator]
---

# Context handover: Layer 3 implementation

## Audit finding

Completed a full code audit of the orchestrator (`orchestrator/`, `tests/`) against the spec and docs.

### What is already there

| Component | Status | Evidence |
|---|---|---|
| `Handover` schema in `state.py` | Defined, never written | `state.py:30-33`, `state.py:85` |
| Token usage capture per iteration | Working | `orchestrator.py:199,324` |
| Context saturation detection | Working (detect only) | `marlin_proxy.py:166-204` |
| `context_saturation_tokens` config | Working (default 120k) | `config.py`, `config.toml` |
| `reconcile.py` git-anchored state | Working (Layer 3 quality) | `reconcile.py:108-134` |
| Single long-lived `ClaudeSDKClient` session | Confirmed | `orchestrator.py:245` (one `async with` for the whole run) |

### What is missing

| Gap | Impact |
|---|---|
| No `handover` action in `ProxyAction` type | No way to trigger handover programmatically |
| `context_saturated()` emits `escalate`, not handover | Context overflow interrupts Marlin instead of auto-recovering |
| No HANDOVER.md authoring logic | Worker never writes the checkpoint document |
| No fresh session spawn path | Even if a doc existed, nothing would consume it |
| `state.handovers[]` never written | Audit trail for handovers is empty |
| Trigger threshold too late (120k, ~60-90% of window) | Quality degrades before trigger fires |

### Layer classification

The existing `reconcile.py` is already **Layer 3** for ongoing state tracking. The handover path itself is not implemented at any layer.

The ROADMAP Theme 5 note says "manual trigger only, no automatic threshold." This plan supersedes that recommendation and targets automatic triggering, for two reasons:

1. The whole point of the proxy is to remove human-in-the-loop on mechanical decisions. Context saturation is fully mechanical.
2. A manual-only trigger requires Marlin to notice `run.log` output and intervene, which is exactly the problem we're solving.

---

## Lumitra cross-check: shared primitive or orchestrator-specific?

The `2026-05-27-feedback-service-lumitra.md` plan and its `intelligence.lumitra.co` spec describe an executor daemon that originally ran the orchestrator (`claude -p` in tmux + worktrees). The **2026-05-28 decision** pivoted the active path to Claude Managed Agents (Anthropic-hosted sandboxes). The self-hosted executor (and therefore the orchestrator) became the **fallback path**.

**Verdict: orchestrator-specific for now, fallback-path for intelligence.lumitra.**

Context handover does NOT need to be extracted as a shared module today. When/if Lumitra reverts to self-hosted execution, the orchestrator is the engine they'd plug in, and it would benefit from handover out of the box. But designing a library interface today for a fallback path that may never activate is premature.

The code belongs in `orchestrator/`, not a separate package.

---

## Design

### Trigger: earlier, automatic, dual-signal

Current: escalate when `input_tokens >= 120_000` (late, blocking).

New: auto-handover when `input_tokens >= context_handover_tokens` (default 80_000, ~50-60% of a 200k window). This fires before quality degrades.

Secondary trigger: sub-goal boundary. When the Worker emits `current_step_id` that matches a natural boundary token (a string ending in `.N.done` or the iteration hits a step transition), the Proxy can issue a handover even if the token threshold has not been crossed. This is Phase B scope; Phase A uses token threshold only.

Config keys (additive, backward-compatible):

```toml
[proxy]
context_handover_tokens = 80000    # new: auto-handover trigger
context_saturation_tokens = 120000 # existing: hard escalation if handover fails
```

### The `handover` Proxy action

`proxy.py` `ProxyAction` gains `"handover"` between `"stop"` and `"escalate"`:

```python
ProxyAction = Literal["reply", "stop", "handover", "escalate"]
```

The `handover` action means: "ask the Worker to write HANDOVER.md, then stop this session and spawn a fresh one seeded with that file."

### HANDOVER.md: structure + authoring

When `marlin_proxy.py` detects `context_saturated(state, config.context_handover_tokens)`, it returns a `ProxyDecision(action="handover", text=HANDOVER_PROMPT, reasoning="context threshold reached")`.

`HANDOVER_PROMPT` instructs the Worker to emit a structured document. The document is **anchored to external verified state**, not self-reported prose:

```
You are approaching context capacity. Before this session ends, write a file
called HANDOVER.md in the task root. Fill every section below from what you
can verify (git log, test output, file contents) -- not from memory.

## GOAL
(copy from state.goal verbatim)

## VERIFIED DONE (git-confirmed)
List only work that appears in `git log {baseline}..HEAD`. For each entry:
- SHA: <commit sha>
- What changed: <files + one-line description>
- Test status: passed / failing / untested (run the test suite if in doubt)

## IN FLIGHT (no commit yet)
Files you touched this iteration that are not committed. List paths + current
state (working/broken/partial).

## NEXT EXACT ACTION
One concrete action the fresh session should take first. Be specific enough
that no rediscovery is needed: file, function, what to change and why.

## OPEN DECISIONS
Unresolved questions the fresh session needs the Proxy to answer before
proceeding. Each on one line: "Q: <question>".

## GOTCHAS
Non-obvious constraints or failure modes you discovered. One line each.

After writing the file, respond with only: HANDOVER_COMPLETE
```

### Fresh session spawn in orchestrator.py

After the Worker writes HANDOVER.md and responds with `HANDOVER_COMPLETE`, the orchestrator loop:

1. Reads `HANDOVER.md` from the task root (fails loudly if missing).
2. Calls `reconcile(state, project_dir)` to capture any remaining git state.
3. Appends a `Handover` entry to `state.handovers` with `at_turn`, `reason`, and `doc` path.
4. Saves `state.json`.
5. Closes the current `ClaudeSDKClient` session by exiting the `async with` block.
6. Starts a new `ClaudeSDKClient` session with the HANDOVER.md contents as the initial user message, plus a header: `"Resuming task from handover. The following checkpoint was written by the previous session and verified against git:"`.
7. Continues the same outer loop (iteration counter resets to 0 for the new leg, but `max_iterations` is the same).

State continuity: `state.goal`, `state.commits`, `state.files_touched`, `state.decisions`, `state.handovers` all persist across legs. The only thing that resets is the in-memory `ClaudeSDKClient`.

### Verification: what "done" means before crossing the handover

Before step 6 above, the orchestrator verifies the checkpoint against git:

```python
def verify_handover_doc(doc: str, state: State, project_dir: Path) -> list[str]:
    """Return a list of discrepancies between the HANDOVER doc's VERIFIED DONE
    section and actual git state. Empty list = clean."""
    ...
```

If discrepancies exist, the orchestrator logs them to `run.log` and appends a warning section to the HANDOVER.md before seeding the fresh session. The fresh session sees the warning and can correct course. The handover still proceeds (better a warned fresh session than an escalation).

### What the fresh session receives

The fresh session's first turn is:

```
[HANDOVER FROM PREVIOUS SESSION - turn {N}, input_tokens {T}]

The previous session verified and wrote the following checkpoint.
Note: git reconciliation found <N discrepancies> — see DISCREPANCY section.

<contents of HANDOVER.md>

Continue from NEXT EXACT ACTION. Call update_state("commit") after each
commit. Call the Proxy if you hit a decision from OPEN DECISIONS.
```

---

## Implementation plan

### Phase A: manual + auto trigger, anchored doc, fresh session (this PR)

Estimated effort: 3-4 hours.

**A1. `proxy.py`**: add `"handover"` to `ProxyAction`. No other changes.

**A2. `config.py`**: add `context_handover_tokens: int = 80_000` to the proxy config section. Keep `context_saturation_tokens = 120_000` as the hard escalation fallback.

**A3. `marlin_proxy.py`**: change `context_saturated()` handler to return `handover` action (not `escalate`). Keep the hard `context_saturation_tokens` path as escalation fallback in case the Worker fails to produce `HANDOVER_COMPLETE` within 3 iterations after receiving the handover prompt.

**A4. `orchestrator/handover.py`**: new module. Three functions:
- `build_handover_prompt(state: State) -> str`: returns the Worker instruction.
- `verify_handover_doc(doc: str, state: State, project_dir: Path) -> list[str]`: cross-checks HANDOVER.md VERIFIED DONE section against `reconcile` output.
- `seed_fresh_session_message(doc_path: Path, state: State, discrepancies: list[str]) -> str`: builds the first message for the fresh session.

**A5. `orchestrator.py`**: handle `decision.action == "handover"` in the main loop. After Worker writes HANDOVER.md:
- Call `reconcile`.
- Call `verify_handover_doc`.
- Append `Handover` to `state.handovers`, save state.
- Exit the inner `async with ClaudeSDKClient` block.
- Re-enter `async with ClaudeSDKClient` with fresh options, seed from HANDOVER.md.
- Continue outer loop.

**A6. Tests**: add `tests/test_handover.py` covering:
- `verify_handover_doc` detects a missing SHA.
- `seed_fresh_session_message` includes the discrepancy warning when present.
- Integration test: mock SDK returns `HANDOVER_COMPLETE`, orchestrator spawns second session.

**A7. Config file update**: add `context_handover_tokens` to the default `config.toml` template with a comment explaining the 50-60% rule.

### Phase B: sub-goal boundary trigger (follow-up, not this PR)

When Theme 4 (stagnation detection) lands, the Proxy has `current_step_id` transitions as a signal. Add a second trigger path: issue `handover` at step boundaries regardless of token count if the step just completed is flagged as a natural handover point in the goal file frontmatter.

---

## Files changed

| File | Change |
|---|---|
| `orchestrator/proxy.py` | Add `"handover"` to `ProxyAction` literal |
| `orchestrator/config.py` | Add `context_handover_tokens = 80_000` |
| `orchestrator/marlin_proxy.py` | Change saturation response to `handover`; add hard fallback |
| `orchestrator/handover.py` | New module (prompt builder, verifier, seed builder) |
| `orchestrator/orchestrator.py` | Handle `handover` action in main loop |
| `orchestrator/state.py` | No change (schema already correct) |
| `tests/test_handover.py` | New test file |
| `config.toml` (template) | Add `context_handover_tokens` |
| `ROADMAP.md` | Move Theme 5 from `queued` to `in-progress` |

---

## What changes for the operator

No breaking changes. Existing runs below 80k tokens behave identically.

For runs that cross 80k tokens: instead of receiving an escalation, Marlin gets a `run.log` line `[handover] spawning fresh leg N` and the run continues. If the Worker fails to produce `HANDOVER_COMPLETE` within 3 turns, the system falls back to escalation (preserving the existing behavior as the safety net).

`orchestrator status --task-id <id>` will show `legs: N` when a handover occurred.

---

## Not in scope

- Resume CLI (`orchestrator resume`): still deferred. Handover is within a single `orchestrator run` invocation.
- Compact-in-place (summarization, same session): still deferred. Phase A's fresh-session approach is simpler and more reliable.
- Phase B sub-goal boundary trigger: requires Theme 4 first.
- intelligence.lumitra.co integration: active path uses Managed Agents, not this code. Revisit if the fallback executor is activated.
