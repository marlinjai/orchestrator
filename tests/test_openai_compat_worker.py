"""E4: the OpenAI-compatible worker adapter (the Mercury worker behind the gate).

A scripted ChatStream plus a fake clock drives the real session: tool-call
reassembly across stream deltas, the per-call latency split (TTFT, generation,
tool, provider server time), usage mapping, worktree confinement of every file
tool, the command denylist and env scrub, update_state through the shared
handler, the tool-round cap, and the provider forward's error classification.
"""

import json
import shutil
import stat
from pathlib import Path

import pytest

from orchestrator.adapters.openai_compat_worker import (
    OpenAICompatWorkerAdapter,
    OpenAICompatWorkerSession,
    ProviderError,
    build_system_prompt,
    forward_chat_stream,
)
from orchestrator.executor import ExecutorProfile
from orchestrator.retry import is_transient_sdk_error
from orchestrator.state import State, load_state, save_state
from orchestrator.worker import WORKER_SYSTEM_PROMPT

PROFILE = ExecutorProfile(role="worker", model_id="mercury-2", provider="inception")


class _Clock:
    def __init__(self, step: float = 0.1):
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def _tool_call_events(name: str, args: dict, *, split: int = 3, call_id: str = "c1"):
    """A tool call streamed as `split` argument fragments, then finish + usage."""
    text = json.dumps(args)
    size = max(1, len(text) // split)
    frags = [text[i : i + size] for i in range(0, len(text), size)]
    events = [
        {
            "model": "mercury-2",
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [
                            {"index": 0, "id": call_id, "function": {"name": name, "arguments": frags[0]}}
                        ],
                    }
                }
            ],
        }
    ]
    for frag in frags[1:]:
        events.append(
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": frag}}]}}]}
        )
    events.append({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]})
    events.append(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 40,
                "prompt_tokens_details": {"cached_tokens": 200},
            },
            "server_timing": {"server_latency_ms": 350.4},
        }
    )
    return events


def _text_events(text: str):
    return [
        {"model": "mercury-2", "choices": [{"delta": {"role": "assistant", "content": text[:4]}}]},
        {"choices": [{"delta": {"content": text[4:]}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 500, "completion_tokens": 10}},
    ]


class _ScriptedChat:
    """A ChatStream that answers each model call with the next scripted event list."""

    def __init__(self, *calls):
        self.calls = list(calls)
        self.bodies: list[dict] = []

    def __call__(self, body):
        self.bodies.append(json.loads(json.dumps(body)))  # snapshot, history mutates later
        yield from self.calls.pop(0)


def _session(tmp_path: Path, chat, **kw) -> OpenAICompatWorkerSession:
    root = tmp_path / "work"
    root.mkdir(exist_ok=True)
    state_path = tmp_path / "state.json"
    if not state_path.exists():
        save_state(state_path, State(task_id="t", goal="g"))
    return OpenAICompatWorkerSession(
        profile=PROFILE, chat=chat, work_dir=root, state_path=state_path, clock=_Clock(), **kw
    )


# ---- prompt ----


def test_system_prompt_keeps_the_shared_index_rules_verbatim():
    prompt = build_system_prompt()
    rules = WORKER_SYSTEM_PROMPT[
        WORKER_SYSTEM_PROMPT.index("Hard rules") : WORKER_SYSTEM_PROMPT.index("Tool: execute_with_secrets")
    ]
    assert rules in prompt
    assert "Claude Code worker" not in prompt
    assert "execute_with_secrets" not in prompt


# ---- the tool loop ----


async def test_turn_reassembles_streamed_tool_call_and_measures_latency(tmp_path):
    chat = _ScriptedChat(
        _tool_call_events("write_file", {"path": "src/a.py", "content": "x = 1\n"}),
        _text_events("done, wrote a.py"),
    )
    session = _session(tmp_path, chat)
    seen: list[str] = []

    result = await session.run_turn("write a.py", on_text=seen.append)

    assert (tmp_path / "work" / "src" / "a.py").read_text() == "x = 1\n"
    assert result.chunks == ["done, wrote a.py"]
    assert seen == ["done, wrote a.py"]  # once per model call, never per delta
    assert result.model == "mercury-2"
    # Request shape: the forward gets tools, streaming with usage, the model id.
    first = chat.bodies[0]
    assert first["model"] == "mercury-2" and first["stream"] is True
    assert first["stream_options"] == {"include_usage": True}
    assert {t["function"]["name"] for t in first["tools"]} >= {"write_file", "update_state"}
    # The tool result went back to the model under the call's id.
    second = chat.bodies[1]["messages"]
    assert second[-2]["tool_calls"][0]["id"] == "c1"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"
    # Latency: two calls, TTFT and generation measured, tool time on the first.
    assert len(result.calls) == 2
    a, b = result.calls
    assert a.ttft_ms is not None and a.generation_ms is not None and a.response_ms is not None
    assert a.tool_ms is not None and b.tool_ms is None
    assert a.server_ms == 350
    assert a.output_tokens == 40 and b.output_tokens == 10
    # Usage: cached prompt tokens split out of input.
    assert result.input_tokens == (1000 - 200) + 500
    assert result.cache_read_tokens == 200
    assert result.output_tokens == 50


async def test_history_persists_across_turns(tmp_path):
    chat = _ScriptedChat(_text_events("first answer"), _text_events("second answer"))
    session = _session(tmp_path, chat)
    await session.run_turn("one")
    await session.run_turn("two")
    contents = [m.get("content") for m in chat.bodies[1]["messages"]]
    assert "one" in contents and "first answer" in contents and contents[-1] == "two"


async def test_tool_round_cap_ends_the_turn_visibly(tmp_path):
    loop_forever = [
        _tool_call_events("list_dir", {}, call_id=f"c{i}") for i in range(3)
    ]
    session = _session(tmp_path, _ScriptedChat(*loop_forever), max_tool_rounds=2)
    result = await session.run_turn("go")
    assert "2 tool rounds" in result.chunks[-1]
    assert len(result.calls) == 2


# ---- confinement ----


async def _tool(session, name, args):
    return await session._run_tool(name, json.dumps(args))


async def test_file_tools_refuse_paths_outside_the_work_dir(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    outside = tmp_path / "outside.txt"
    for args in ({"path": "../outside.txt", "content": "x"}, {"path": str(outside), "content": "x"}):
        out = await _tool(session, "write_file", args)
        assert out.startswith("refused")
    assert not outside.exists()
    assert (await _tool(session, "read_file", {"path": "/etc/hosts"})).startswith("refused")


async def test_symlink_out_of_the_work_dir_is_refused(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "work" / "link").symlink_to(elsewhere)
    out = await _tool(session, "write_file", {"path": "link/evil.txt", "content": "x"})
    assert out.startswith("refused")
    assert not (elsewhere / "evil.txt").exists()


async def test_edit_file_requires_a_unique_match(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    f = tmp_path / "work" / "f.txt"
    f.write_text("a a b")
    assert "matches 2 times" in await _tool(session, "edit_file", {"path": "f.txt", "old_string": "a", "new_string": "c"})
    assert "not found" in await _tool(session, "edit_file", {"path": "f.txt", "old_string": "z", "new_string": "c"})
    assert (await _tool(session, "edit_file", {"path": "f.txt", "old_string": "b", "new_string": "c"})).startswith("ok")
    assert f.read_text() == "a a c"
    await _tool(session, "edit_file", {"path": "f.txt", "old_string": "a", "new_string": "d", "replace_all": True})
    assert f.read_text() == "d d c"


async def test_run_command_runs_in_the_work_dir_with_a_scrubbed_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "proxy-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    session = _session(tmp_path, _ScriptedChat())
    out = await _tool(
        session,
        "run_command",
        {"command": 'pwd; echo "[${SECRETS_PROXY_TOKEN:-}${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}]"'},
    )
    assert out.startswith("exit code 0")
    assert str((tmp_path / "work").resolve()) in out
    assert "[]" in out and "secret" not in out


async def test_run_command_honors_the_denylist(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    out = await _tool(session, "run_command", {"command": "rm -rf ."})
    assert out.startswith("refused by the orchestrator's command denylist")


async def test_bad_tool_arguments_are_reported_to_the_model(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    assert "not valid JSON" in await session._run_tool("write_file", "{nope")
    assert "unknown tool" in await session._run_tool("delete_repo", "{}")
    assert "bad arguments" in await _tool(session, "write_file", {"path": "a.txt"})


async def test_update_state_goes_through_the_shared_handler(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    out = await _tool(session, "update_state", {"kind": "open_thread", "thread": "ask about the schema"})
    assert out.startswith("ok")
    assert load_state(tmp_path / "state.json").open_threads == ["ask about the schema"]


# ---- the provider forward transport ----


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")


def _session_stub(path: Path, script: list[dict]) -> Path:
    """A node script standing in for ``secrets-proxy-call forward-session``.

    It appends ``SPAWN <argv>`` and then every request line to a trace file, and
    answers request N (counted across restarts, through the trace) with
    ``script[N]``: ``frames`` (written as given, with ``"id": "$id"`` replaced
    by the request's id), then optionally ``hang`` (answer nothing more) or
    ``exit`` (a code, with ``stderr`` written first).
    """
    trace = path.with_suffix(".trace")
    path.write_text(
        f"""const fs = require("fs");
const readline = require("readline");
const trace = {json.dumps(str(trace))};
const script = {json.dumps(script)};
fs.appendFileSync(trace, "SPAWN " + process.argv.slice(2).join(",") + "\\n");
const served = () => fs.readFileSync(trace, "utf8").split("\\n").filter((l) => l.startsWith("{{")).length;
readline.createInterface({{ input: process.stdin }}).on("line", (line) => {{
  const step = script[served()] || {{}};
  fs.appendFileSync(trace, line + "\\n");
  const id = JSON.parse(line).id;
  for (const frame of step.frames || []) {{
    process.stdout.write(JSON.stringify(frame.id === "$id" ? {{ ...frame, id }} : frame) + "\\n");
  }}
  if (step.stderr) process.stderr.write(step.stderr);
  if (step.exit !== undefined) process.exit(step.exit);
}});
if (script.length && script[0].exit_at_start !== undefined) {{
  process.stderr.write(script[0].stderr || "");
  process.exit(script[0].exit_at_start);
}}
"""
    )
    return trace


def _ok(*chunks: str) -> dict:
    """A scripted 200 answer whose body arrives as the given chunks."""
    return {
        "frames": [{"id": "$id", "chunk": c} for c in chunks]
        + [{"id": "$id", "end": {"status": 200}}]
    }


_HI = 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'


@needs_node
def test_forward_session_serves_every_call_through_one_process(tmp_path):
    cli = tmp_path / "cli.js"
    trace = _session_stub(
        cli, [_ok(_HI, ": keep-alive\n\n", "data: [DONE]\n\n"), _ok(_HI + "data: [DONE]\n\n")]
    )
    stream = forward_chat_stream("inception", cli_path=str(cli))
    try:
        assert list(stream({"model": "mercury-2"})) == [{"choices": [{"delta": {"content": "hi"}}]}]
        assert list(stream({"model": "mercury-2", "n": 2})) == [
            {"choices": [{"delta": {"content": "hi"}}]}
        ]
    finally:
        stream.close()
    spawn, first, second = trace.read_text().splitlines()
    # One process for both calls: the point of the session.
    assert spawn == "SPAWN forward-session,/forward/inception/chat/completions"
    assert json.loads(first) == {"id": 1, "body": {"model": "mercury-2"}}
    assert json.loads(second) == {"id": 2, "body": {"model": "mercury-2", "n": 2}}


@needs_node
def test_forward_session_reassembles_events_split_across_chunks(tmp_path):
    cli = tmp_path / "cli.js"
    _session_stub(cli, [_ok('data: {"choi', 'ces":[]}\n', '\ndata: {"a":1}\n\n')])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    try:
        # No [DONE]: a 2xx end frame closes the stream just as well.
        assert list(stream({})) == [{"choices": []}, {"a": 1}]
    finally:
        stream.close()


@needs_node
def test_forward_session_skips_the_tail_of_an_abandoned_call(tmp_path):
    cli = tmp_path / "cli.js"
    late = {"frames": [{"id": 1, "chunk": 'data: {"stale":true}\n\n'}] + _ok(_HI)["frames"]}
    _session_stub(cli, [{"frames": [{"id": "$id", "chunk": _HI}]}, late])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    try:
        first = stream({})
        assert next(first) == {"choices": [{"delta": {"content": "hi"}}]}
        first.close()  # read enough; the next call abandons it
        assert list(stream({})) == [{"choices": [{"delta": {"content": "hi"}}]}]
    finally:
        stream.close()


@needs_node
@pytest.mark.parametrize(
    ("error", "transient"),
    [
        ("429: rate limited", True),
        ("HTTP 503 overloaded", True),
        ("connect ECONNREFUSED 100.124.97.31:8765", True),
        # A port that looks like an HTTP status must not mask a network failure.
        ("connect ETIMEDOUT 10.0.0.5:443", True),
        ("fetch failed", True),
        # Terminal statuses and unclassified failures are not retried.
        ("400: prompt is too long", False),
        ("no machine-identity credentials for org lumitra", False),
    ],
)
def test_forward_session_error_frames_carry_an_explicit_transient_flag(tmp_path, error, transient):
    cli = tmp_path / "cli.js"
    _session_stub(cli, [{"frames": [{"id": "$id", "error": error}]}, _ok(_HI)])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    try:
        with pytest.raises(ProviderError) as info:
            list(stream({"model": "mercury-2"}))
        assert info.value.transient is transient
        assert is_transient_sdk_error(info.value) is transient
        # A failed call does not end the session: the retry reuses the process.
        assert list(stream({})) == [{"choices": [{"delta": {"content": "hi"}}]}]
    finally:
        stream.close()


@needs_node
@pytest.mark.parametrize(("status", "transient"), [(429, True), (503, True), (400, False), (403, False)])
def test_forward_session_non_2xx_end_reports_status_and_body(tmp_path, status, transient):
    cli = tmp_path / "cli.js"
    frames = [
        {"id": "$id", "chunk": '{"error":"the provider said no"}'},
        {"id": "$id", "end": {"status": status}},
    ]
    _session_stub(cli, [{"frames": frames}])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    try:
        with pytest.raises(ProviderError, match=f"HTTP {status}: .*the provider said no") as info:
            list(stream({}))
        assert info.value.transient is transient
    finally:
        stream.close()


@needs_node
def test_forward_session_stall_is_a_transient_timeout_and_the_retry_restarts_it(tmp_path):
    cli = tmp_path / "cli.js"
    trace = _session_stub(cli, [{"frames": []}, _ok(_HI)])
    stream = forward_chat_stream("inception", cli_path=str(cli), timeout_s=0.5)
    try:
        with pytest.raises(ProviderError, match="timed out") as info:
            list(stream({"model": "mercury-2"}))
        assert info.value.transient is True
        assert list(stream({})) == [{"choices": [{"delta": {"content": "hi"}}]}]
    finally:
        stream.close()
    assert [line.split()[0] for line in trace.read_text().splitlines()].count("SPAWN") == 2


@needs_node
def test_forward_session_process_exit_is_classified_by_its_stderr(tmp_path):
    cli = tmp_path / "cli.js"
    _session_stub(cli, [{"exit": 1, "stderr": "secrets-proxy-call: connect ECONNREFUSED 1.2.3.4:8765\n"}])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    with pytest.raises(ProviderError, match="ECONNREFUSED") as info:
        list(stream({}))
    assert info.value.transient is True


@needs_node
def test_forward_session_names_a_cli_too_old_for_the_mode(tmp_path):
    cli = tmp_path / "cli.js"
    usage = "secrets-proxy-call: unknown command forward-session\nusage: ...\n"
    _session_stub(cli, [{"exit_at_start": 2, "stderr": usage}])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    with pytest.raises(ProviderError, match="older than its forward-session mode") as info:
        list(stream({}))
    assert info.value.transient is False


@needs_node
def test_forward_malformed_event_is_terminal(tmp_path):
    cli = tmp_path / "cli.js"
    _session_stub(cli, [_ok("data: {not json\n\n")])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    try:
        with pytest.raises(ProviderError, match="malformed") as info:
            list(stream({"model": "mercury-2"}))
        assert info.value.transient is False
    finally:
        stream.close()


def test_forward_without_the_cli_is_terminal(monkeypatch):
    monkeypatch.setattr("orchestrator.adapters.openai_compat_worker.resolve_proxy_cli", lambda: None)
    stream = forward_chat_stream("inception")
    with pytest.raises(ProviderError, match="CLI not found") as info:
        list(stream({"model": "mercury-2"}))
    assert info.value.transient is False


@needs_node
def test_forward_session_close_ends_the_process_and_is_repeatable(tmp_path):
    cli = tmp_path / "cli.js"
    trace = _session_stub(cli, [_ok(_HI), _ok(_HI)])
    stream = forward_chat_stream("inception", cli_path=str(cli))
    list(stream({}))
    proc = stream._proc
    stream.close()
    stream.close()
    assert proc.poll() is not None
    # A call after close starts a fresh process rather than failing.
    assert list(stream({})) == [{"choices": [{"delta": {"content": "hi"}}]}]
    stream.close()
    assert trace.read_text().count("SPAWN") == 2


async def test_adapter_closes_its_transport_when_the_session_ends(tmp_path):
    class _Closable(_ScriptedChat):
        closed = 0

        def close(self) -> None:
            self.closed += 1

    chat = _Closable()
    adapter = OpenAICompatWorkerAdapter(
        profile=PROFILE, work_dir=tmp_path, state_path=tmp_path / "state.json", chat=chat
    )
    async with adapter.open():
        assert chat.closed == 0
    assert chat.closed == 1
    # A transport without close (a test double, a plain function) is fine too.
    plain = OpenAICompatWorkerAdapter(
        profile=PROFILE, work_dir=tmp_path, state_path=tmp_path / "state.json", chat=lambda body: iter(())
    )
    async with plain.open():
        pass


async def test_every_tool_call_is_audited_next_to_state(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    await _tool(session, "write_file", {"path": "a.txt", "content": "secret-ish body"})
    await _tool(session, "run_command", {"command": "cat ../state.json"})
    await _tool(session, "read_file", {"path": "/etc/hosts"})
    lines = [json.loads(line) for line in session.audit_path.read_text().splitlines()]
    assert session.audit_path == tmp_path / "worker-tools.jsonl"
    assert [e["tool"] for e in lines] == ["write_file", "run_command", "read_file"]
    assert lines[0]["args"]["content"] == "<15 characters>"
    assert lines[1]["args"]["command"] == "cat ../state.json"
    assert lines[2]["result"].startswith("refused")


async def test_audit_file_is_secured_even_if_it_pre_existed_world_readable(tmp_path):
    audit_path = tmp_path / "worker-tools.jsonl"
    audit_path.write_text("")
    audit_path.chmod(0o644)
    session = _session(tmp_path, _ScriptedChat())
    await _tool(session, "write_file", {"path": "a.txt", "content": "x"})
    assert stat.S_IMODE(audit_path.stat().st_mode) == 0o600


# ---- observed actions keep the self-report in step with git ----


async def test_tool_calls_record_their_files_and_commits(tmp_path):
    import subprocess

    from orchestrator.reconcile import reconcile

    session = _session(tmp_path, _ScriptedChat())
    root = tmp_path / "work"
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "seed.txt").write_text("seed")
    subprocess.run([*git, "add", "-A"], cwd=root, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "seed"], cwd=root, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    state = load_state(tmp_path / "state.json")
    state.baseline_ref = base
    save_state(tmp_path / "state.json", state)

    await _tool(session, "write_file", {"path": "src/a.py", "content": "x = 1\n"})
    out = await _tool(
        session,
        "run_command",
        {"command": 'git add -A && git -c user.email=t@example.invalid -c user.name=t commit -q -m "feat: a"'},
    )
    assert out.startswith("exit code 0")

    state = load_state(tmp_path / "state.json")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    assert [(c.sha, c.message, c.decided_by) for c in state.commits] == [(head, "feat: a", "proxy")]
    assert [f.path for f in state.files_touched] == ["src/a.py"]
    # Reconcile finds nothing the Worker did not report.
    assert reconcile(state, root) == (0, 0)


async def test_failed_commit_and_refused_write_record_nothing(tmp_path):
    session = _session(tmp_path, _ScriptedChat())
    await _tool(session, "write_file", {"path": "../escape.txt", "content": "x"})
    await _tool(session, "run_command", {"command": "git commit -m nothing"})  # not a repo: exit != 0
    state = load_state(tmp_path / "state.json")
    assert state.commits == [] and state.files_touched == []


async def test_read_stops_once_the_call_is_complete(tmp_path):
    """A provider that holds a finished stream open must not stall the Worker:
    once a finish reason and the usage chunk are in, reading stops and the
    stream is closed."""
    closed = []

    def stalling_chat(body):
        def gen():
            try:
                yield from _text_events("done")
                raise AssertionError("read past the usage chunk (the provider stall)")
            finally:
                closed.append(True)

        return gen()

    session = _session(tmp_path, stalling_chat)
    result = await session.run_turn("go")
    assert result.chunks == ["done"]
    assert closed == [True]
    # response_ms is the full wall time of the call (clock reads: sent, 4 events, done)
    assert result.calls[0].response_ms is not None


# ---- stalled or empty provider answers are retried in place ----


async def test_empty_answer_is_retried_in_place(tmp_path, monkeypatch):
    import orchestrator.adapters.openai_compat_worker as mod

    monkeypatch.setattr(mod, "CALL_RETRY_BACKOFF_S", 0)
    empty = [{"choices": [{"delta": {}, "finish_reason": "stop"}]}, {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 0}}]
    chat = _ScriptedChat(empty, _text_events("real answer"))
    session = _session(tmp_path, chat)
    result = await session.run_turn("go")
    assert result.chunks == ["real answer"]
    assert len(chat.bodies) == 2
    # The retry sent the same conversation, not a new turn.
    assert chat.bodies[0]["messages"] == chat.bodies[1]["messages"]


async def test_transient_failure_is_retried_then_surfaces(tmp_path, monkeypatch):
    import orchestrator.adapters.openai_compat_worker as mod

    monkeypatch.setattr(mod, "CALL_RETRY_BACKOFF_S", 0)
    calls = []

    def failing_chat(body):
        calls.append(1)
        raise ProviderError("stream stalled", transient=True)

    session = _session(tmp_path, failing_chat)
    with pytest.raises(ProviderError, match="stalled"):
        await session.run_turn("go")
    assert len(calls) == 1 + mod.CALL_RETRIES


async def test_terminal_failure_is_not_retried(tmp_path):
    calls = []

    def bad_request(body):
        calls.append(1)
        raise ProviderError("HTTP 400", transient=False)

    session = _session(tmp_path, bad_request)
    with pytest.raises(ProviderError):
        await session.run_turn("go")
    assert len(calls) == 1


# ---- M9 token watcher: peak context and the early end of a turn ----


async def test_turn_reports_peak_context_and_ends_at_the_threshold(tmp_path):
    big = _tool_call_events("list_dir", {}, call_id="c1")
    big[-1]["usage"] = {"prompt_tokens": 90_000, "completion_tokens": 5}
    chat = _ScriptedChat(
        _tool_call_events("list_dir", {}, call_id="c0"), big, _text_events("never reached")
    )
    session = _session(tmp_path, chat, context_limit=89_600)
    result = await session.run_turn("go")
    assert result.context_tokens == 90_000
    assert "handover threshold" in result.chunks[-1]
    assert len(chat.bodies) == 2  # the third call never happened
    # The history stays valid for the handover prompt: the last assistant tool
    # call already has its tool result.
    assert session.messages[-1]["role"] == "tool"


async def test_no_threshold_means_no_early_end(tmp_path):
    big = _tool_call_events("list_dir", {}, call_id="c1")
    big[-1]["usage"] = {"prompt_tokens": 500_000, "completion_tokens": 5}
    session = _session(tmp_path, _ScriptedChat(big, _text_events("finished")))
    result = await session.run_turn("go")
    assert result.chunks[-1] == "finished"


async def test_checkpoint_turn_is_not_ended_at_the_threshold(tmp_path):
    big = _tool_call_events("list_dir", {}, call_id="c1")
    big[-1]["usage"] = {"prompt_tokens": 90_000, "completion_tokens": 5}
    chat = _ScriptedChat(big, _text_events("HANDOVER_COMPLETE"))
    session = _session(tmp_path, chat, context_limit=89_600)
    result = await session.run_turn("write the handover", checkpoint=True)
    assert result.chunks[-1] == "HANDOVER_COMPLETE"
    assert len(chat.bodies) == 2  # the checkpoint turn ran to its final reply
