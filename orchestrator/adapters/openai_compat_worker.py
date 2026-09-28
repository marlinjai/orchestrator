"""OpenAI-compatible worker adapter (E4): a hand-rolled tool loop behind the WorkerPort.

Runs a coding Worker on any provider whose chat-completions API speaks the
OpenAI shape with tool calling (Inception's ``mercury-2`` first), reached ONLY
through the secrets proxy's provider forward, so this process never holds the
provider key (docs/plans/2026-07-24-hexagonal-executor-ports.md, E4).

What the Claude SDK gives the Claude adapter for free is built here explicitly:

- **Tools**: ``read_file``, ``write_file``, ``edit_file``, ``list_dir``,
  ``run_command`` and ``update_state`` (the same schema and handler as the
  Claude Worker's MCP tool), all confined to the attempt's work dir.
- **Confinement**: every file tool resolves its path through
  ``worker.path_outside_root``, the one check the Claude adapter's
  ``can_use_tool`` guard also uses. ``run_command`` runs with ``cwd`` at the work
  dir, the orchestrator's bash denylist, a timeout, capped output and an env
  scrubbed of provider and proxy credentials. Like the Claude guard it cannot
  stop a shell command from writing outside the work dir; the git reconcile and
  the held-out verifier are the backstops.
- **Telemetry**: the provider forward streams, so each model call's
  time-to-first-token, generation time, tool time and the provider-reported
  server latency are measured directly (``CallLatency``), which is what the E4
  Claude vs Mercury comparison is decided on.

Failure is loud, never a silent swap to Claude: a provider error raises
``ProviderError`` (with an explicit ``transient`` flag the loop's retry
classifier honors), because crediting a Claude-produced result to Mercury would
corrupt the experiment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator

from orchestrator.executor import (
    DEFAULT_PROXY_CLI,
    PROVIDER_FORWARD_ROUTES,
    PROXY_CLI_ENV,
    ExecutorProfile,
    resolve_proxy_cli,
)
from orchestrator.guardrails import bash_allowed
from orchestrator.ports import OnText, TurnResult
from orchestrator.state import CallLatency
from orchestrator.tools import (
    UPDATE_STATE_DESCRIPTION,
    UPDATE_STATE_SCHEMA,
    build_update_state_handler,
)
from orchestrator.worker import (
    WORKER_SYSTEM_PROMPT,
    path_outside_root,
)

logger = logging.getLogger(__name__)

Clock = Callable[[], float]

# One request body in, the stream's parsed JSON event objects out, in order.
ChatStream = Callable[[dict], Iterator[dict]]

# HTTP statuses worth a backoff-and-retry of the leg; anything else is terminal.
TRANSIENT_HTTP_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})

MAX_TOOL_ROUNDS = 60
COMMAND_TIMEOUT_S = 600
MAX_TOOL_OUTPUT_CHARS = 30_000
TOOL_AUDIT_FILE = "worker-tools.jsonl"
AUDIT_RESULT_CHARS = 500

# A malformed or unterminated SSE stream must not grow one buffered line without bound.
_MAX_SSE_LINE_BYTES = 1 << 20

# A denylist can't keep up with whatever secret the orchestrator's own launch
# environment happens to carry (DATABASE_URL, a notify webhook, ...); only these
# non-secret runtime variables are handed to a command the model runs.
_COMMAND_ENV_ALLOWLIST = frozenset({"PATH", "LANG", "LC_ALL", "TMPDIR", "HOME"})


class ProviderError(RuntimeError):
    """A provider or transport failure. ``transient`` says whether the loop may
    retry the leg (rate limit, overload, network) or must fail the run."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


_HTTP_STATUS_RE = re.compile(r"\b([45]\d\d)\b")
_NETWORK_FAILURE_RE = re.compile(
    r"unreachable|ECONN|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|timed? ?out|socket hang up|fetch failed",
    re.IGNORECASE,
)


def _cli_failure(returncode: int, stderr: str) -> ProviderError:
    """Classify a failed ``secrets-proxy-call forward`` run: a retryable HTTP
    status or a network-level failure is transient, anything else is terminal."""
    reason = stderr.strip()[:300]
    if _NETWORK_FAILURE_RE.search(reason):
        transient = True
    else:
        match = _HTTP_STATUS_RE.search(reason)
        transient = bool(match) and int(match.group(1)) in TRANSIENT_HTTP_STATUSES
    return ProviderError(
        f"secrets-proxy-call forward exited {returncode}: {reason}", transient=transient
    )


def forward_chat_stream(
    provider: str,
    *,
    cli_path: str | None = None,
    timeout_s: float = 300.0,
) -> ChatStream:
    """The production ChatStream: pipe the request body into the
    secrets-proxy-call CLI's ``forward`` subcommand for ``provider`` and yield
    each SSE ``data:`` event it relays as parsed JSON until ``[DONE]``.

    The CLI mints its own short-lived token from the operator's machine
    identity, so this process holds neither the provider key nor a proxy token.
    """
    route = PROVIDER_FORWARD_ROUTES[provider]

    def stream(body: dict) -> Iterator[dict]:
        resolved = cli_path if cli_path is not None else resolve_proxy_cli()
        if not resolved:
            raise ProviderError(
                f"secrets-proxy-call CLI not found (looked for ${PROXY_CLI_ENV} or "
                f"{DEFAULT_PROXY_CLI}); cannot reach the provider forward",
                transient=False,
            )
        try:
            proc = subprocess.Popen(
                ["node", str(resolved), "forward", route],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            raise ProviderError(f"secrets-proxy-call forward failed to run: {e}", transient=True) from e
        # The proxy stream ends when the CLI exits; a stalled stream is killed
        # after timeout_s so a hung forward cannot wedge the run.
        timed_out = threading.Event()

        def _kill_on_timeout() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout_s, _kill_on_timeout)
        timer.start()
        stderr_chunks: list[bytes] = []
        stderr_thread = threading.Thread(
            target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True
        )
        stderr_thread.start()
        try:
            try:
                proc.stdin.write(json.dumps(body).encode("utf-8"))
                proc.stdin.close()
            except OSError:
                pass  # the CLI died early; its exit status below carries the reason
            while True:
                raw = proc.stdout.readline(_MAX_SSE_LINE_BYTES + 1)
                if not raw:
                    break
                if len(raw) > _MAX_SSE_LINE_BYTES:
                    raise ProviderError("provider stream line exceeds 1 MiB", transient=False)
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError as e:
                    raise ProviderError(
                        f"malformed stream event: {data[:200]!r}", transient=False
                    ) from e
            returncode = proc.wait()
            stderr_thread.join(timeout=5)
            if timed_out.is_set():
                raise ProviderError(
                    f"provider stream timed out after {timeout_s:g}s", transient=True
                )
            if returncode != 0:
                raise _cli_failure(
                    returncode, b"".join(stderr_chunks).decode("utf-8", errors="replace")
                )
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                pipe.close()

    return stream


def build_system_prompt() -> str:
    """The Claude Worker's system prompt with its hard rules and shared-index
    discipline kept byte-identical; only the Claude-specific opener and the
    execute_with_secrets section (a tool this adapter does not offer) change."""
    rules_end = WORKER_SYSTEM_PROMPT.index("Tool: execute_with_secrets")
    shared = WORKER_SYSTEM_PROMPT[:rules_end].replace(
        "You are an autonomous Claude Code worker.", "You are an autonomous coding worker.", 1
    )
    return shared + (
        "Tools: read_file, write_file, edit_file, list_dir and run_command work only\n"
        "inside your assigned work directory; paths outside it are refused. Use\n"
        "run_command for git, tests and builds. Commands that need secrets are not\n"
        "available to you: if the task needs one, say so as your final message and stop.\n"
    )


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOLS: list[dict] = [
    _fn(
        "read_file",
        "Read a text file in the work directory. Optional 1-based line offset and line limit.",
        {
            "path": {"type": "string"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"},
        },
        ["path"],
    ),
    _fn(
        "write_file",
        "Create or overwrite a file in the work directory with the given content.",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _fn(
        "edit_file",
        "Replace old_string with new_string in a file. old_string must match exactly "
        "and be unique unless replace_all is true.",
        {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        ["path", "old_string", "new_string"],
    ),
    _fn(
        "list_dir",
        "List the entries of a directory in the work directory (default: its root).",
        {"path": {"type": "string"}},
        [],
    ),
    _fn(
        "run_command",
        "Run a shell command (bash) with the work directory as cwd. Returns the exit "
        "code and combined output, truncated when long.",
        {"command": {"type": "string"}, "timeout_s": {"type": "integer"}},
        ["command"],
    ),
    {
        "type": "function",
        "function": {
            "name": "update_state",
            "description": UPDATE_STATE_DESCRIPTION,
            "parameters": UPDATE_STATE_SCHEMA,
        },
    },
]


# A `key: value` / `key=value` pair whose key names a credential, and known
# bare-token prefixes (OpenAI/Anthropic `sk-`, GitHub `gh[a-z]_`, AWS `AKIA`,
# a JWT's `eyJ` header). Audited tool args/results can carry any of these
# (a command that curls with a bearer header, a file the model reads that
# holds a `.env`), so they are redacted before the line is ever written.
_SECRET_KV_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|access[_-]?key|"
    r"authorization|bearer)(\s*[:=]\s*)(['\"]?)([A-Za-z0-9_\-\./+]{6,})\3"
)
_SECRET_BARE_RE = re.compile(
    r"\b(sk-[A-Za-z0-9]{10,}|gh[opsu]_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|"
    r"AKIA[A-Z0-9]{12,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,})\b"
)


def _redact_secrets(value: Any) -> Any:
    """Mask credential-shaped substrings in a string, or recursively in a
    JSON-like structure. Leaves everything else untouched."""
    if isinstance(value, str):
        redacted = _SECRET_KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]{m.group(3)}", value)
        return _SECRET_BARE_RE.sub("[REDACTED]", redacted)
    if isinstance(value, dict):
        return {k: _redact_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_secrets(v) for v in value]
    return value


def _truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated: {len(text) - limit} more characters]"


def _ms(seconds: float) -> int:
    return max(0, int(seconds * 1000))


@dataclass
class _ModelCall:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    latency: CallLatency = field(default_factory=CallLatency)
    usage: dict | None = None
    model: str | None = None


class OpenAICompatWorkerSession:
    """One Worker conversation: the message history persists across turns."""

    def __init__(
        self,
        *,
        profile: ExecutorProfile,
        chat: ChatStream,
        work_dir: Path,
        state_path: Path,
        clock: Clock = time.monotonic,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
        command_timeout_s: int = COMMAND_TIMEOUT_S,
    ) -> None:
        self._profile = profile
        self._chat = chat
        self._root = work_dir.resolve()
        self._clock = clock
        self._max_tool_rounds = max_tool_rounds
        self._command_timeout_s = command_timeout_s
        self._update_state = build_update_state_handler(state_path)
        # Audit trail of every tool call, next to state.json. The Claude Worker
        # leaves a full transcript; this is the Mercury Worker's equivalent, so
        # a command that reached outside its assignment is visible afterwards.
        self.audit_path = state_path.parent / TOOL_AUDIT_FILE
        self.messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]

    async def run_turn(self, user_message: str, *, on_text: OnText | None = None) -> TurnResult:
        self.messages.append({"role": "user", "content": user_message})
        result = TurnResult()
        for _ in range(self._max_tool_rounds):
            call = await asyncio.to_thread(self._call_model)
            # One on_text per model call, not per stream delta: the loop prefixes
            # every on_text with "worker:", and Mercury's delta boundaries fall
            # mid-word, so per-delta output interleaved prefixes into the text.
            if call.content and on_text is not None:
                on_text(call.content)
            self._account(result, call)
            assistant: dict[str, Any] = {"role": "assistant", "content": call.content or None}
            if call.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in call.tool_calls
                ]
            self.messages.append(assistant)
            if not call.tool_calls:
                return result
            tools_started = self._clock()
            for tc in call.tool_calls:
                output = await self._run_tool(tc["name"], tc["arguments"])
                self.messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": output}
                )
            call.latency.tool_ms = _ms(self._clock() - tools_started)
        # Out of tool rounds: end the turn visibly instead of failing the run, so
        # the Decision Proxy sees the cap and the loop's own iteration cap governs.
        note = (
            f"[turn ended by the orchestrator: {self._max_tool_rounds} tool rounds "
            "reached before the model finished]"
        )
        logger.warning("openai-compat worker: %s", note)
        result.chunks.append(note)
        if on_text is not None:
            on_text(note)
        return result

    def _account(self, result: TurnResult, call: _ModelCall) -> None:
        if call.content:
            result.chunks.append(call.content)
        result.calls.append(call.latency)
        if call.model and not result.model:
            result.model = call.model
        u = call.usage or {}
        prompt = int(u.get("prompt_tokens") or 0)
        details = u.get("prompt_tokens_details") or {}
        cached = int(details.get("cached_tokens") or 0) if isinstance(details, dict) else 0
        result.input_tokens += max(0, prompt - cached)
        result.cache_read_tokens += cached
        result.output_tokens += int(u.get("completion_tokens") or 0)

    def _request_body(self) -> dict:
        body: dict[str, Any] = {
            "model": self._profile.model_id,
            "messages": self.messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self._profile.reasoning_effort is not None:
            body["reasoning_effort"] = self._profile.reasoning_effort
        return body

    def _call_model(self) -> _ModelCall:
        """One streamed model call, run in a worker thread (blocking I/O)."""
        call = _ModelCall()
        pending: dict[int, dict] = {}
        parts: list[str] = []
        sent = self._clock()
        first: float | None = None
        last: float | None = None
        for event in self._chat(self._request_body()):
            now = self._clock()
            call.model = call.model or event.get("model")
            if isinstance(event.get("usage"), dict):
                call.usage = event["usage"]
            timing = event.get("server_timing")
            if isinstance(timing, dict) and isinstance(timing.get("server_latency_ms"), (int, float)):
                call.latency.server_ms = int(timing["server_latency_ms"])
            produced = False
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    parts.append(text)
                    produced = True
                for frag in delta.get("tool_calls") or []:
                    slot = pending.setdefault(
                        int(frag.get("index") or 0), {"id": None, "name": "", "arguments": ""}
                    )
                    if frag.get("id"):
                        slot["id"] = frag["id"]
                    fn = frag.get("function") or {}
                    if fn.get("name") and not slot["name"]:
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
                    produced = True
            if produced:
                first = now if first is None else first
                last = now
        done = self._clock()
        call.content = "".join(parts)
        call.tool_calls = [
            {
                "id": slot["id"] or f"call_{index}",
                "name": slot["name"],
                "arguments": slot["arguments"] or "{}",
            }
            for index, slot in sorted(pending.items())
        ]
        if first is not None and last is not None:
            call.latency.ttft_ms = _ms(first - sent)
            call.latency.generation_ms = _ms(last - first)
        call.latency.response_ms = _ms((last if last is not None else done) - sent)
        if call.usage and isinstance(call.usage.get("completion_tokens"), int):
            call.latency.output_tokens = call.usage["completion_tokens"]
        return call

    # ---- tools ----

    async def _run_tool(self, name: str, raw_args: str) -> str:
        output = await self._dispatch_tool(name, raw_args)
        self._audit(name, raw_args, output)
        return output

    def _audit(self, name: str, raw_args: str, output: str) -> None:
        """Append one JSON line per tool call. File contents are recorded by
        size only (the diff is in git); commands, paths and results are kept,
        but redacted (``_redact_secrets``): a command or a file the model reads
        or writes can carry a live credential, and this file is not a secret
        store."""
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            args = {"unparsed": _redact_secrets(raw_args[:500])}
        if isinstance(args, dict):
            for size_only_field in ("content", "old_string", "new_string"):
                value = args.get(size_only_field)
                if isinstance(value, str):
                    args[size_only_field] = f"<{len(value)} characters>"
            args = _redact_secrets(args)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": name,
            "args": args,
            "result": _redact_secrets(output[:AUDIT_RESULT_CHARS]),
        }
        try:
            fd = os.open(str(self.audit_path), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                os.close(fd)
                raise
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except OSError as e:
            logger.warning("could not write the worker tool audit %s: %s", self.audit_path, e)

    async def _dispatch_tool(self, name: str, raw_args: str) -> str:
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError as e:
            return f"error: arguments for {name} are not valid JSON ({e})"
        if not isinstance(args, dict):
            return f"error: arguments for {name} must be a JSON object"
        try:
            if name == "update_state":
                res = await self._update_state(args)
                return "".join(c.get("text", "") for c in res.get("content", []))
            if name == "run_command":
                return await asyncio.to_thread(self._run_command, args)
            if name == "read_file":
                return self._read_file(args)
            if name == "write_file":
                return self._write_file(args)
            if name == "edit_file":
                return self._edit_file(args)
            if name == "list_dir":
                return self._list_dir(args)
        except (KeyError, TypeError) as e:
            return f"error: bad arguments for {name}: {e}"
        except OSError as e:
            return f"error: {name} failed: {e}"
        return f"error: unknown tool {name!r}"

    def _confined(self, raw: str | None) -> Path:
        """Resolve a tool path inside the work dir, or raise PermissionError."""
        raw = raw or "."
        outside = path_outside_root(raw, self._root)
        if outside is not None:
            raise PermissionError(
                f"refused: {raw} resolves to {outside}, outside the work directory {self._root}"
            )
        p = Path(raw)
        return (p if p.is_absolute() else self._root / p).resolve()

    def _read_file(self, args: dict) -> str:
        try:
            path = self._confined(args["path"])
        except PermissionError as e:
            return str(e)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(args.get("offset") or 1))
        limit = args.get("limit")
        chosen = lines[start - 1 : start - 1 + int(limit)] if limit else lines[start - 1 :]
        numbered = "\n".join(f"{start + i}\t{line}" for i, line in enumerate(chosen))
        return _truncate(numbered) or "(empty file)"

    def _write_file(self, args: dict) -> str:
        try:
            path = self._confined(args["path"])
        except PermissionError as e:
            return str(e)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = args["content"]
        path.write_text(content, encoding="utf-8")
        return f"ok: wrote {len(content)} characters to {path.relative_to(self._root)}"

    def _edit_file(self, args: dict) -> str:
        try:
            path = self._confined(args["path"])
        except PermissionError as e:
            return str(e)
        text = path.read_text(encoding="utf-8")
        old, new = args["old_string"], args["new_string"]
        count = text.count(old) if old else 0
        if count == 0:
            return "error: old_string not found in the file"
        if count > 1 and not args.get("replace_all"):
            return f"error: old_string matches {count} times; make it unique or set replace_all"
        path.write_text(text.replace(old, new) if args.get("replace_all") else text.replace(old, new, 1), encoding="utf-8")
        return f"ok: replaced {count if args.get('replace_all') else 1} occurrence(s)"

    def _list_dir(self, args: dict) -> str:
        try:
            path = self._confined(args.get("path"))
        except PermissionError as e:
            return str(e)
        entries = sorted(
            f"{child.name}/" if child.is_dir() else child.name for child in path.iterdir()
        )
        return _truncate("\n".join(entries)) or "(empty directory)"

    def _run_command(self, args: dict) -> str:
        command = args["command"]
        allowed, reason = bash_allowed(command)
        if not allowed:
            return f"refused by the orchestrator's command denylist: {reason}"
        timeout = min(int(args.get("timeout_s") or self._command_timeout_s), self._command_timeout_s)
        env = {k: v for k, v in os.environ.items() if k in _COMMAND_ENV_ALLOWLIST}
        # Output goes to disk, not a pipe: a model-chosen command (`yes`, `cat` on
        # a huge file) can otherwise buffer gigabytes in this process before the
        # timeout fires, since capture_output holds the whole thing in memory.
        with tempfile.TemporaryFile() as out:
            try:
                proc = subprocess.run(
                    ["/bin/bash", "-c", command],
                    cwd=self._root,
                    env=env,
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return f"error: command timed out after {timeout}s"
            out.seek(0)
            output = out.read(MAX_TOOL_OUTPUT_CHARS * 4).decode("utf-8", errors="replace")
        return f"exit code {proc.returncode}\n{_truncate(output)}"


class OpenAICompatWorkerAdapter:
    """WorkerAdapter for OpenAI-compatible providers reached through the
    secrets proxy's provider forward. Selected only behind the E4 gate (a
    held-out verifier must be configured, see ``adapters.resolve_worker_adapter``)."""

    def __init__(
        self,
        *,
        profile: ExecutorProfile,
        work_dir: Path,
        state_path: Path,
        chat: ChatStream | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self._profile = profile
        self._work_dir = work_dir
        self._state_path = state_path
        self._chat = chat or forward_chat_stream(profile.provider)
        self._clock = clock

    @asynccontextmanager
    async def open(self) -> AsyncIterator[OpenAICompatWorkerSession]:
        yield OpenAICompatWorkerSession(
            profile=self._profile,
            chat=self._chat,
            work_dir=self._work_dir,
            state_path=self._state_path,
            clock=self._clock,
        )
