import asyncio
import json
from dataclasses import dataclass
from typing import Literal, get_args

from claude_agent_sdk import ClaudeAgentOptions, query

from orchestrator.config import CATEGORIES, MarlinProxyConfig
from orchestrator.state import State
from orchestrator.transcript import AssistantTurn, extract_text


MarlinChoice = Literal["auto_approve", "auto_defer", "escalate"]


@dataclass
class MarlinDecision:
    choice: MarlinChoice      # what the orchestrator should actually do
    category: str
    reason: str
    effective_mode: str       # resolved mode for the category: off|live|shadow|escalate
    proxy_choice: MarlinChoice  # what the persona judged (differs from choice in shadow)
    executed: bool            # True only when an auto-action was actually taken


MARLIN_SYSTEM_PROMPT = """\
You are the Marlin Proxy. The Decision Proxy already decided the Worker's next
step requires Marlin's input (an escalation). You answer one question: would
Marlin auto-approve this, defer it, or is it genuinely his call?

Classify the escalation into exactly one category and pick a choice. Emit a
single JSON object with this exact shape, nothing after it:

  {"choice": "auto_approve" | "auto_defer" | "escalate",
   "category": "<one category>",
   "reason": "<one terse line, no em-dashes or en-dashes>"}

choice:
- auto_approve: proceed as the Worker proposed (Marlin would say "go ahead").
- auto_defer: not today's priority, leave it for Marlin (he would say "machen wir anschliessend").
- escalate: genuinely Marlin's call, interrupt him.

Decide from the persona and the provided state alone. When unsure between
auto_defer and escalate, choose escalate: interrupting Marlin is cheaper than
deferring his actual priority. You may use Read and Grep to verify a codebase
claim (e.g. is a branch merged), but never to settle a question of taste.
"""


def build_marlin_prompt(
    *,
    persona: str,
    state: State,
    escalation_text: str,
    recent_turns: list[AssistantTurn],
) -> str:
    turns_text = "\n\n---\n\n".join(t.text for t in recent_turns) or "(no recent assistant turns)"
    decisions_text = "\n".join(
        f"- turn {d.turn}: Q: {d.question} -> A: {d.answer}" for d in state.decisions
    ) or "(none)"
    last_usage = state.usage[-1] if state.usage else None
    tokens_in = last_usage.input_tokens if last_usage else 0
    return f"""\
## Persona

{persona}

## Goal

{state.goal}

## Current state

- iteration: {state.iteration} / {state.max_iterations}
- current_step_id: {state.current_step_id}
- files_touched: {[f.path for f in state.files_touched]}
- commits: {[c.sha[:8] for c in state.commits]}
- open_threads: {state.open_threads}
- last_iteration_input_tokens: {tokens_in}
- prior decisions:
{decisions_text}

## What the Decision Proxy escalated

{escalation_text}

## Worker's recent turns

{turns_text}

## Your job

Classify and decide. Emit JSON per the system instructions.
"""


def parse_marlin_output(raw: str) -> tuple[MarlinChoice, str, str]:
    """Parse the persona's JSON. On any failure, return a safe escalate/unknown
    so a malformed model response never silently auto-approves.
    """
    valid_choices = set(get_args(MarlinChoice))
    start = raw.find("{")
    if start == -1:
        return "escalate", "unknown", "persona emitted no JSON"
    try:
        data, _ = json.JSONDecoder().raw_decode(raw, start)
    except json.JSONDecodeError as e:
        return "escalate", "unknown", f"persona emitted invalid JSON: {e}"
    choice = data.get("choice")
    if choice not in valid_choices:
        return "escalate", "unknown", f"persona emitted bad choice: {choice!r}"
    category = data.get("category")
    if category not in CATEGORIES:
        category = "unknown"
    reason = data.get("reason", "")
    return choice, category, reason


def resolve_marlin_decision(
    *,
    config: MarlinProxyConfig,
    category: str,
    proxy_choice: MarlinChoice,
    reason: str,
) -> MarlinDecision:
    """Pure resolution of the persona's judgment against config. No I/O, no LLM.

    - effective escalate: orchestrator interrupts Marlin, persona choice ignored.
    - effective shadow: orchestrator interrupts Marlin, but the persona's would-be
      choice is preserved for the ledger (executed=False).
    - effective live: the persona's choice stands; executed when it's an action
      (auto_approve / auto_defer), not when the persona itself chose escalate.
    """
    effective = config.effective_mode(category)

    if effective == "escalate":
        return MarlinDecision(
            choice="escalate",
            category=category,
            reason=reason,
            effective_mode="escalate",
            proxy_choice=proxy_choice,
            executed=False,
        )
    if effective == "shadow":
        return MarlinDecision(
            choice="escalate",
            category=category,
            reason=reason,
            effective_mode="shadow",
            proxy_choice=proxy_choice,
            executed=False,
        )
    # live
    executed = proxy_choice in ("auto_approve", "auto_defer")
    return MarlinDecision(
        choice=proxy_choice,
        category=category,
        reason=reason,
        effective_mode="live",
        proxy_choice=proxy_choice,
        executed=executed,
    )


def context_saturated(state: State, threshold: int) -> bool:
    if not state.usage:
        return False
    return state.usage[-1].input_tokens >= threshold


def _escalate(category: str, reason: str) -> MarlinDecision:
    return MarlinDecision(
        choice="escalate",
        category=category,
        reason=reason,
        effective_mode="escalate",
        proxy_choice="escalate",
        executed=False,
    )


async def run_marlin_decision(
    *,
    config: MarlinProxyConfig,
    persona: str,
    state: State,
    escalation_text: str,
    recent_turns: list[AssistantTurn] | None = None,
) -> MarlinDecision:
    recent_turns = recent_turns or []

    # Kill switch: emergency stop, force escalate without spending tokens.
    if config.kill_switch_path.exists():
        return _escalate("unknown", "marlin-proxy kill switch active")

    # Context saturation: fast path before any LLM call. Handover execution is
    # Phase 5, so for now a saturated context always escalates rather than
    # silently running deeper into the Dumb Zone.
    if context_saturated(state, config.context_saturation_tokens):
        tokens = state.usage[-1].input_tokens
        return _escalate(
            "context_saturation",
            f"context saturated ({tokens} tokens), handover not yet automated",
        )

    prompt = build_marlin_prompt(
        persona=persona,
        state=state,
        escalation_text=escalation_text,
        recent_turns=recent_turns,
    )
    options = ClaudeAgentOptions(
        system_prompt=MARLIN_SYSTEM_PROMPT,
        setting_sources=[],
        allowed_tools=["Read", "Grep", "Glob"],
    )

    async def _collect() -> str:
        chunks: list[str] = []
        async for msg in query(prompt=prompt, options=options):
            text = extract_text(msg)
            if text:
                chunks.append(text)
        return "".join(chunks)

    timeout_s = config.per_decision_timeout_ms / 1000
    try:
        raw = await asyncio.wait_for(_collect(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return _escalate("unknown", f"persona call timed out after {timeout_s:.0f}s")

    proxy_choice, category, reason = parse_marlin_output(raw)
    return resolve_marlin_decision(
        config=config,
        category=category,
        proxy_choice=proxy_choice,
        reason=reason,
    )
