import json
import re
from dataclasses import dataclass
from typing import Literal

from claude_agent_sdk import ClaudeAgentOptions, query

from orchestrator.state import State
from orchestrator.transcript import AssistantTurn


ProxyAction = Literal["reply", "stop", "escalate"]


@dataclass
class ProxyDecision:
    action: ProxyAction
    text: str
    reasoning: str


PROXY_SYSTEM_PROMPT = """\
You are Marlin's autonomous decision proxy. A Worker agent is running on a task.
You read the Worker's most recent output and decide what Marlin would say back.

You may use Read, Grep, and WebSearch to gather context before deciding (e.g.,
to verify library versions, pricing, API shapes). Use them sparingly: simple
"should I proceed?" questions need no research, only context-heavy decisions
do.

You MUST emit your final decision as a JSON object with this exact shape:

  {"action": "reply" | "stop" | "escalate",
   "text": "...",
   "reasoning": "..."}

- "reply": continue the work. `text` is the message Marlin would send back.
- "stop": the task is genuinely complete. `text` may be empty.
- "escalate": a human decision is required (money, comms, irreversible action,
  or scope ambiguity you cannot resolve). `text` describes what the human needs
  to decide.

Wrap the JSON in a fenced code block if you want; the orchestrator will extract
it. Do not output anything after the JSON.
"""


def build_proxy_prompt(
    *,
    persona: str,
    state: State,
    recent_turns: list[AssistantTurn],
) -> str:
    turns_text = "\n\n---\n\n".join(t.text for t in recent_turns) or "(no recent assistant turns)"
    decisions_text = "\n".join(
        f"- turn {d.turn}: Q: {d.question} -> A: {d.answer}"
        for d in state.decisions
    ) or "(none)"
    return f"""\
## Persona

{persona}

## Goal

{state.goal}

## Current state

- iteration: {state.iteration} / {state.max_iterations}
- current_step_id: {state.current_step_id}
- files_touched: {state.files_touched}
- open_threads: {state.open_threads}
- prior decisions:
{decisions_text}

## Worker's last {len(recent_turns)} assistant turns

{turns_text}

## Your job

Read what the Worker just said. Decide reply / stop / escalate. Emit JSON per
the system instructions.
"""


def parse_proxy_output(raw: str) -> ProxyDecision:
    json_match = re.search(r"\{[\s\S]*?\}", raw)
    if not json_match:
        return ProxyDecision(
            action="escalate",
            text="proxy emitted no JSON",
            reasoning=f"raw output: {raw[:200]}",
        )
    try:
        data = json.loads(json_match.group(0))
        action = data.get("action")
        if action not in ("reply", "stop", "escalate"):
            raise ValueError(f"bad action: {action}")
        return ProxyDecision(
            action=action,
            text=data.get("text", ""),
            reasoning=data.get("reasoning", ""),
        )
    except Exception as e:
        return ProxyDecision(
            action="escalate",
            text="proxy emitted invalid JSON",
            reasoning=f"{e}: {raw[:200]}",
        )


async def run_proxy_decision(
    *,
    persona: str,
    state: State,
    recent_turns: list[AssistantTurn],
) -> ProxyDecision:
    prompt = build_proxy_prompt(persona=persona, state=state, recent_turns=recent_turns)
    options = ClaudeAgentOptions(
        system_prompt=PROXY_SYSTEM_PROMPT,
        setting_sources=[],
        allowed_tools=["Read", "Grep", "Glob", "WebSearch", "WebFetch"],
    )
    chunks: list[str] = []
    async for msg in query(prompt=prompt, options=options):
        text = _extract_text(msg)
        if text:
            chunks.append(text)
    return parse_proxy_output("".join(chunks))


def _extract_text(msg) -> str:
    """Extract text from any SDK message shape. Adapt at smoke-test time."""
    if isinstance(msg, dict):
        content = msg.get("message", {}).get("content")
        if isinstance(content, list):
            return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        if isinstance(content, str):
            return content
    if hasattr(msg, "content"):
        c = msg.content
        if isinstance(c, list):
            return "".join(getattr(b, "text", "") for b in c)
        if isinstance(c, str):
            return c
    return ""
