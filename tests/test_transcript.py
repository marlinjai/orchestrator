from pathlib import Path
from orchestrator.transcript import (
    AssistantTurn,
    extract_text,
    last_assistant_text,
    last_n_turns,
    parse_transcript,
)

FIXTURE = Path(__file__).parent / "fixtures" / "transcript_sample.jsonl"


def test_parse_transcript_returns_all_messages():
    msgs = parse_transcript(FIXTURE)
    assert len(msgs) == 4


def test_last_assistant_text_returns_most_recent_text_block():
    msgs = parse_transcript(FIXTURE)
    text = last_assistant_text(msgs)
    assert text == "Done. Should I proceed?"


def test_last_assistant_text_empty_when_no_assistant():
    text = last_assistant_text([])
    assert text == ""


def test_last_n_turns_returns_only_assistant_text_turns():
    msgs = parse_transcript(FIXTURE)
    turns = last_n_turns(msgs, n=10)
    assert all(isinstance(t, AssistantTurn) for t in turns)
    assert [t.text for t in turns] == ["I will do it.", "Done. Should I proceed?"]


def test_last_n_turns_caps_at_n():
    msgs = parse_transcript(FIXTURE)
    turns = last_n_turns(msgs, n=1)
    assert len(turns) == 1
    assert turns[0].text == "Done. Should I proceed?"


def test_parse_transcript_skips_corrupt_lines(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"a"}]}}\n'
        "not json at all\n"
        '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"b"}]}}\n'
    )
    msgs = parse_transcript(p)
    assert len(msgs) == 2


def test_extract_text_from_dict_message():
    msg = {"message": {"content": [{"type": "text", "text": "hello"}, {"type": "tool_use"}]}}
    assert extract_text(msg) == "hello"


def test_extract_text_from_dict_string_content():
    msg = {"message": {"content": "raw"}}
    assert extract_text(msg) == "raw"


def test_extract_text_returns_empty_for_unknown_shape():
    assert extract_text({}) == ""
    assert extract_text(None) == ""


class _FakeMsgWithContent:
    def __init__(self, content):
        self.content = content


def test_extract_text_from_object_with_content():
    msg = _FakeMsgWithContent([type("B", (), {"text": "world"})()])
    assert extract_text(msg) == "world"
