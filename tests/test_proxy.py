from pathlib import Path
import pytest
from orchestrator.proxy import (
    ProxyDecision,
    build_proxy_prompt,
    parse_proxy_output,
)
from orchestrator.state import State
from orchestrator.transcript import AssistantTurn


def test_build_proxy_prompt_includes_persona_goal_state_turns():
    state = State(task_id="t1", goal="ship the thing", iteration=3)
    turns = [AssistantTurn(text="step 1 done"), AssistantTurn(text="should I proceed?")]
    prompt = build_proxy_prompt(
        persona="approve reasonable scope",
        state=state,
        recent_turns=turns,
    )
    assert "approve reasonable scope" in prompt
    assert "ship the thing" in prompt
    assert "should I proceed?" in prompt
    assert "step 1 done" in prompt
    assert "iteration" in prompt.lower()


def test_parse_proxy_output_reply():
    raw = '{"action": "reply", "text": "yes proceed", "reasoning": "scope is fine"}'
    decision = parse_proxy_output(raw)
    assert decision.action == "reply"
    assert decision.text == "yes proceed"
    assert decision.reasoning == "scope is fine"


def test_parse_proxy_output_stop():
    raw = '{"action": "stop", "reasoning": "task complete"}'
    decision = parse_proxy_output(raw)
    assert decision.action == "stop"
    assert decision.text == ""


def test_parse_proxy_output_escalate():
    raw = '{"action": "escalate", "text": "human needed", "reasoning": "money"}'
    decision = parse_proxy_output(raw)
    assert decision.action == "escalate"


def test_parse_proxy_output_extracts_json_from_prose():
    raw = 'Here is my decision:\n```json\n{"action": "reply", "text": "ok", "reasoning": "r"}\n```\nDone.'
    decision = parse_proxy_output(raw)
    assert decision.action == "reply"
    assert decision.text == "ok"


def test_parse_proxy_output_invalid_falls_back_to_escalate():
    raw = "I cannot decide."
    decision = parse_proxy_output(raw)
    assert decision.action == "escalate"


def test_parse_proxy_output_handles_nested_json():
    raw = '{"action": "reply", "text": "ok", "reasoning": "r", "context": {"nested": "yes"}}'
    decision = parse_proxy_output(raw)
    assert decision.action == "reply"
    assert decision.text == "ok"


def test_build_proxy_prompt_handles_empty_turns():
    state = State(task_id="t1", goal="g")
    prompt = build_proxy_prompt(persona="p", state=state, recent_turns=[])
    assert "(no recent assistant turns)" in prompt
