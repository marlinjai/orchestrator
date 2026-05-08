import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AssistantTurn:
    text: str


def parse_transcript(path: Path) -> list[dict]:
    if not path.exists():
        return []
    msgs: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msgs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return msgs


def _get_role(msg: dict) -> str:
    """Return the message role, checking both top-level and nested locations.

    Real Claude Code transcripts nest role inside msg["message"]["role"] and
    also expose a top-level "type" field ("user", "assistant"). Some legacy or
    synthetic transcripts may put "role" at the top level. Check all of them.
    """
    role = msg.get("role")
    if isinstance(role, str) and role:
        return role
    nested = msg.get("message")
    if isinstance(nested, dict):
        nested_role = nested.get("role")
        if isinstance(nested_role, str) and nested_role:
            return nested_role
    top_type = msg.get("type")
    if isinstance(top_type, str) and top_type in ("user", "assistant", "system"):
        return top_type
    return ""


def _assistant_text_blocks(msg: dict) -> list[str]:
    content = msg.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return []
    return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]


def last_assistant_text(msgs: list[dict]) -> str:
    for m in reversed(msgs):
        if _get_role(m) != "assistant":
            continue
        blocks = _assistant_text_blocks(m)
        if blocks:
            return blocks[-1]
    return ""


def last_n_turns(msgs: list[dict], n: int) -> list[AssistantTurn]:
    turns: list[AssistantTurn] = []
    for m in msgs:
        if _get_role(m) != "assistant":
            continue
        for text in _assistant_text_blocks(m):
            if text:
                turns.append(AssistantTurn(text=text))
    return turns[-n:]


def extract_text(msg) -> str:
    """Extract text content from any SDK message shape (dict or object).

    Handles both message dict envelopes (from ClaudeSDKClient) and message objects with .content.
    Returns empty string when no text is present.
    """
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
