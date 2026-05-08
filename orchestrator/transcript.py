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


def _assistant_text_blocks(msg: dict) -> list[str]:
    content = msg.get("message", {}).get("content", [])
    return [b.get("text", "") for b in content if b.get("type") == "text"]


def last_assistant_text(msgs: list[dict]) -> str:
    for m in reversed(msgs):
        if m.get("role") != "assistant":
            continue
        blocks = _assistant_text_blocks(m)
        if blocks:
            return blocks[-1]
    return ""


def last_n_turns(msgs: list[dict], n: int) -> list[AssistantTurn]:
    turns: list[AssistantTurn] = []
    for m in msgs:
        if m.get("role") != "assistant":
            continue
        for text in _assistant_text_blocks(m):
            if text:
                turns.append(AssistantTurn(text=text))
    return turns[-n:]
