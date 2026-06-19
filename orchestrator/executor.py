"""Per-role executor profiles and the one non-Anthropic executor path (Mercury recon).

This is the Wave-2 "per-role model routing" SEAM, deliberately the smallest
slice that the rest of the multi-model plan flips on. It is NOT a model registry
and NOT a set of provider adapters (the roadmap's named #1 scope-creep risk).

Two pieces:

1. ``ExecutorProfile`` + ``resolve_executor(role)``: an operator-owned mapping
   from a ROLE (``worker`` / ``recon`` / ``planner`` / ...) to a model + auth
   mode + optional cost ceiling. Config lives in
   ``~/.config/orchestrator/config.toml`` under ``[executors.<role>]``, the same
   operator-owned, never-goal-authored trust posture as the Marlin Proxy config.
   With NO config, every role resolves to Claude (``CLAUDE_MODEL_ID`` +
   subscription auth) -- byte-for-byte the current single-model behavior. Call
   sites speak in ROLES; model names never leak into them (the roadmap's
   "skills speak in roles" rule).

2. ``run_mercury_recon(...)``: a thin, read-only Mercury (Inception) client used
   ONLY for reconnaissance. It runs NO tools, writes NO files, touches NO repo.
   The Inception API key is injected SERVER-SIDE on the ai-host secrets proxy, so
   the orchestrator process and any transcript only ever see the completion text,
   never the key. If the key/proxy is unavailable it FAILS LOUD and the caller
   falls back to Claude recon (see ``recon_executor`` / the wiring in the
   orchestrator), never silently skipping and never blocking the run.

Transport note (the architectural decision the spec asks us to resolve and
document): a Mercury completion is CONTENT, not a secret, so the secrets-proxy
``/execute`` endpoint -- which redacts output with deterministic regex and then
SUMMARIZES it through a local Ollama model -- is the WRONG transport for getting
a usable completion back (a long token / UUID in the answer would be
``[REDACTED]``, and the Ollama summary discards the verbatim text entirely). So
the Mercury path uses a dedicated RAW-FORWARD transport: the orchestrator POSTs
the chat request to a forward endpoint that injects the Inception key
server-side (``INCEPTION_API_KEY`` from Infisical) and streams back the RAW
completion. The key never enters the orchestrator process env or the transcript;
only the completion text crosses the wire. The transport is a small injectable
seam (``MercuryTransport``) so tests run with a fake and the production default
keeps the key server-side. This composes with ``worker.apply_env_contract``'s
foreign-key scrub rather than fighting it: the orchestrator never holds the key,
so there is nothing for the scrub to leak.
"""

from __future__ import annotations

import json
import logging
import os
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, get_args

from orchestrator.worker import AuthMode

logger = logging.getLogger(__name__)


# The default Claude model id. Every role resolves to this when no executor is
# configured, so a config-free run is the current single-model behavior exactly.
# This is the ONE place the default model name lives; call sites speak in roles.
CLAUDE_MODEL_ID = "claude-opus-4-8"

# The canonical role names the orchestrator routes by. New roles can be added
# here as the plan grows; they all default to Claude until an operator config
# points one at another model.
KNOWN_ROLES: frozenset[str] = frozenset({"worker", "recon", "planner"})

# Mercury (Inception) model id used for the read-only recon path. Only relevant
# when an operator config explicitly points the `recon` role at it.
MERCURY_MODEL_ID = "mercury"

# The Infisical coordinates the secrets proxy uses to inject the Inception key
# server-side. Operator-owned and env-overridable; the orchestrator never reads
# the value, only names the location so the proxy can resolve it. The project id
# defaults to the providers location used across the fleet; scaffold the actual
# key per the report (see INCEPTION_KEY_NAME).
INCEPTION_KEY_NAME = "INCEPTION_API_KEY"
INCEPTION_PROJECT_ID = os.environ.get(
    "ORCHESTRATOR_INCEPTION_PROJECT_ID", "7a3a1f4e-6e0e-4b6a-9d3a-0b9b9c8d7e6f"
)
INCEPTION_SECRET_PATH = os.environ.get("ORCHESTRATOR_INCEPTION_PATH", "/providers")
INCEPTION_SECRET_ENV = os.environ.get("ORCHESTRATOR_INCEPTION_ENV", "production")
INCEPTION_ENDPOINT = os.environ.get(
    "ORCHESTRATOR_INCEPTION_ENDPOINT", "https://api.inceptionlabs.ai/v1/chat/completions"
)

# The secrets-proxy coordinates (same Tailscale-only host the Worker MCP +
# notify already use). The Mercury raw-forward goes through this proxy so the
# Inception key is injected server-side and never touches this process.
PROXY_URL_ENV = "SECRETS_PROXY_URL"
PROXY_TOKEN_ENV = "SECRETS_PROXY_TOKEN"
DEFAULT_PROXY_URL = "http://100.124.97.31:8765"


def _config_home() -> Path:
    override = os.environ.get("ORCHESTRATOR_CONFIG_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "orchestrator"


@dataclass(frozen=True)
class ExecutorProfile:
    """Which model + auth a given ROLE runs on, plus an optional cost ceiling.

    ``role`` is the routing key (``worker`` / ``recon`` / ``planner`` / ...).
    ``model_id`` is the model string. ``auth_mode`` reuses the Worker's existing
    ``AuthMode`` (``subscription`` keeps Claude on the flat login; ``api_key``
    bills the metered API -- the same load-bearing billing switch). ``cost_ceiling_usd``
    is an optional per-role advisory ceiling, ``None`` for "no ceiling".

    ``is_claude`` is the judge-path invariant: the Worker and both Proxies must
    keep running Claude (their integrity is the whole trust model), so callers
    assert ``resolve_executor(<judge role>).is_claude``.
    """

    role: str
    model_id: str
    auth_mode: AuthMode = "subscription"
    cost_ceiling_usd: float | None = None

    @property
    def is_claude(self) -> bool:
        return self.model_id == CLAUDE_MODEL_ID

    @property
    def is_mercury(self) -> bool:
        return self.model_id == MERCURY_MODEL_ID


def _claude_profile(role: str) -> ExecutorProfile:
    """The default profile for any role: Claude on subscription auth, no ceiling.
    A config-free run resolves every role to this, so behavior is unchanged."""
    return ExecutorProfile(role=role, model_id=CLAUDE_MODEL_ID, auth_mode="subscription")


def _coerce_profile(role: str, raw: dict) -> ExecutorProfile:
    """Build an ExecutorProfile from a ``[executors.<role>]`` table. A malformed
    value fails loud (ValueError) so a misconfigured executor never silently
    resolves to a surprise model."""
    model_id = raw.get("model_id", CLAUDE_MODEL_ID)
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError(f"executor[{role}].model_id must be a non-empty string")

    auth_mode = raw.get("auth_mode", "subscription")
    if auth_mode not in get_args(AuthMode):
        raise ValueError(
            f"executor[{role}].auth_mode must be one of {get_args(AuthMode)}, got {auth_mode!r}"
        )

    ceiling = raw.get("cost_ceiling_usd")
    if ceiling is not None:
        if not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool):
            raise ValueError(f"executor[{role}].cost_ceiling_usd must be a number")
        ceiling = float(ceiling)
        if ceiling <= 0:
            ceiling = None

    return ExecutorProfile(
        role=role,
        model_id=model_id.strip(),
        auth_mode=auth_mode,  # type: ignore[arg-type]
        cost_ceiling_usd=ceiling,
    )


def load_executor_config(path: Path | None = None) -> dict[str, ExecutorProfile]:
    """Load the ``[executors]`` section from config.toml. Returns a (possibly
    empty) mapping of role -> ExecutorProfile for the roles the operator pinned.

    Absent file / section => empty mapping (every role then defaults to Claude).
    A malformed value raises ValueError so misconfiguration fails loud. This is
    operator-owned config, NOT goal frontmatter and NOT a per-repo registry
    field: a goal file can never point a role at a non-Claude model.
    """
    cfg_path = path if path is not None else _config_home() / "config.toml"
    if not cfg_path.exists():
        return {}

    try:
        data = tomllib.loads(cfg_path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"config file malformed: {cfg_path}: {e}") from e

    section = data.get("executors", {})
    if not isinstance(section, dict):
        raise ValueError(f"[executors] must be a table in {cfg_path}")

    profiles: dict[str, ExecutorProfile] = {}
    for role, raw in section.items():
        if not isinstance(raw, dict):
            raise ValueError(f"[executors.{role}] must be a table in {cfg_path}")
        profiles[role] = _coerce_profile(role, raw)
    return profiles


def resolve_executor(role: str, *, config_path: Path | None = None) -> ExecutorProfile:
    """Resolve the ExecutorProfile for ``role``.

    DEFAULTS every role to Claude (``CLAUDE_MODEL_ID`` + subscription auth) when
    nothing is configured, so a config-free run is the current single-model
    behavior exactly. An operator config under ``[executors.<role>]`` overrides
    the default for that role only. A malformed config fails loud.
    """
    profiles = load_executor_config(config_path)
    return profiles.get(role, _claude_profile(role))


# --------------------------------------------------------------------------- #
# Mercury (Inception) read-only recon executor
# --------------------------------------------------------------------------- #


@dataclass
class ReconFindings:
    """Structured result of a reconnaissance question.

    ``executor`` records which executor actually served the role (``mercury`` or
    ``claude``) and ``elapsed_ms`` the wall-clock, so a later run can compare a
    Mercury-recon run against a Claude-recon baseline (the
    ``time_to_verified_result`` hook). These are LOGGED telemetry, never a gate
    input. ``ok`` is False on a failure (with ``error`` set) so the caller can
    fall back to Claude recon and surface the failure.
    """

    question: str
    findings: str
    executor: str
    model_id: str
    elapsed_ms: int
    ok: bool = True
    error: str | None = None


class MercuryUnavailable(RuntimeError):
    """Raised when the Mercury path cannot run (no proxy token, proxy error, or a
    malformed Inception response). The caller catches this and falls back to
    Claude recon: a loud failure, never a silent skip."""


# A transport takes the proxy URL, token, and the JSON request body for the
# Inception chat-completions call and returns the RAW completion text. The
# production transport (``_proxy_raw_forward``) injects the Inception key
# server-side on ai-host; tests inject a fake. Keeping this injectable is what
# lets the orchestrator NEVER hold the key while still getting a usable answer.
MercuryTransport = Callable[[str, str, dict], str]


def _build_inception_curl(request_body: dict) -> str:
    """Build the curl command the proxy runs server-side. The Inception key is
    referenced as ``$INCEPTION_API_KEY`` and expands ONLY from the proxy-injected
    env (Infisical), never from this process. The request body is passed via
    stdin (a heredoc) so the JSON -- which may contain the recon question -- can
    never break out into the shell command. stdout is the raw Inception JSON
    response; the proxy returns it verbatim (see _proxy_raw_forward)."""
    body = json.dumps(request_body)
    # The body goes on stdin via a quoted heredoc: no shell expansion inside it,
    # and the only env ref ($INCEPTION_API_KEY) is in the curl args, expanded by
    # the proxy-injected env server-side.
    return (
        "curl -s -X POST "
        f"{INCEPTION_ENDPOINT} "
        '-H "Authorization: Bearer $INCEPTION_API_KEY" '
        '-H "Content-Type: application/json" '
        "--data-binary @- <<'ORCH_MERCURY_EOF'\n"
        f"{body}\n"
        "ORCH_MERCURY_EOF"
    )


def _proxy_raw_forward(proxy_url: str, token: str, request_body: dict) -> str:
    """Production transport: POST the Inception chat request through the secrets
    proxy with the key injected server-side, returning the RAW completion JSON.

    Critically this targets the proxy's RAW-FORWARD endpoint (``/raw``), NOT
    ``/execute``: ``/execute`` redacts and Ollama-summarizes its output, which
    would corrupt a completion (a long token in the answer becomes ``[REDACTED]``
    and the verbatim text is lost). The raw-forward path injects the key the same
    way (``infisical run``) but returns stdout verbatim, so the orchestrator gets
    a usable completion while the key stays server-side.
    """
    body = json.dumps(
        {
            "command": _build_inception_curl(request_body),
            "workingDir": "/tmp",
            "env": INCEPTION_SECRET_ENV,
            "projectId": INCEPTION_PROJECT_ID,
            "path": INCEPTION_SECRET_PATH,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{proxy_url}/raw",
        data=body,
        headers={"Content-Type": "application/json", "X-Proxy-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise MercuryUnavailable(f"secrets-proxy raw-forward failed: {e}") from e

    # The proxy's raw-forward returns the command's stdout (the Inception JSON)
    # under "stdout"; tolerate a bare-string body too for a minimal forward shim.
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if isinstance(data, dict) and "stdout" in data:
        return str(data["stdout"])
    return payload


def _parse_inception_completion(raw: str) -> str:
    """Pull the assistant message text out of an Inception (OpenAI-compatible)
    chat-completions response. Raises MercuryUnavailable on a shape we cannot
    parse so the caller fails loud and falls back to Claude rather than treating
    a malformed/empty answer as a real finding."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise MercuryUnavailable(f"Inception response was not JSON: {raw[:300]!r}") from e
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise MercuryUnavailable(
            f"Inception response missing choices[0].message.content: {raw[:300]!r}"
        ) from e
    if not isinstance(content, str) or not content.strip():
        raise MercuryUnavailable("Inception completion was empty")
    return content.strip()


def run_mercury_recon(
    question: str,
    *,
    profile: ExecutorProfile,
    transport: MercuryTransport | None = None,
    proxy_url: str | None = None,
    proxy_token: str | None = None,
    max_tokens: int = 1024,
) -> ReconFindings:
    """Ask Mercury (Inception) a read-only reconnaissance question and return a
    structured ``ReconFindings``.

    Read-only by construction: this builds one chat-completions request and
    returns the answer text. It runs NO tools, writes NO files, touches NO repo.

    The Inception key is injected SERVER-SIDE by the transport (default
    ``_proxy_raw_forward``); the orchestrator never holds it. If the proxy token
    is absent or the proxy/Inception call fails, this raises ``MercuryUnavailable``
    so the caller falls back to Claude recon. ``elapsed_ms`` + ``executor`` are
    recorded for the ``time_to_verified_result`` comparison (logged, never gated).
    """
    token = proxy_token if proxy_token is not None else os.environ.get(PROXY_TOKEN_ENV)
    if not token:
        raise MercuryUnavailable(
            "secrets-proxy token absent (SECRETS_PROXY_TOKEN); cannot inject the "
            "Inception key server-side"
        )
    url = (
        proxy_url
        if proxy_url is not None
        else os.environ.get(PROXY_URL_ENV, DEFAULT_PROXY_URL)
    ).rstrip("/")
    forward = transport or _proxy_raw_forward

    request_body = {
        "model": profile.model_id,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a read-only reconnaissance assistant. Answer the "
                    "question concisely with concrete findings. You have no tools "
                    "and cannot modify any system."
                ),
            },
            {"role": "user", "content": question},
        ],
    }

    start = time.monotonic()
    raw = forward(url, token, request_body)
    findings = _parse_inception_completion(raw)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return ReconFindings(
        question=question,
        findings=findings,
        executor="mercury",
        model_id=profile.model_id,
        elapsed_ms=elapsed_ms,
        ok=True,
    )


def recon(
    question: str,
    *,
    config_path: Path | None = None,
    claude_recon: Callable[[str], str] | None = None,
    transport: MercuryTransport | None = None,
    proxy_token: str | None = None,
) -> ReconFindings:
    """Run a read-only reconnaissance question through the resolved ``recon``
    executor, falling back to Claude recon on any Mercury failure.

    This is the ONE real call site of the seam: it resolves ``recon`` (Claude by
    default), and ONLY when an operator config points it at Mercury does the
    non-Claude path run. A ``MercuryUnavailable`` (no proxy token, proxy error,
    malformed Inception response) FAILS LOUD into a logged warning and a Claude
    recon fallback -- never a silent skip, never a blocked run.

    ``claude_recon`` is the Claude recon function (question -> findings text). It
    is injected so the orchestrator can wire its own Claude call (the Decision
    Proxy's own model) without this module importing the SDK. When the resolved
    executor is already Claude, it is used directly.
    """
    profile = resolve_executor("recon", config_path=config_path)

    if profile.is_mercury:
        try:
            result = run_mercury_recon(
                question, profile=profile, transport=transport, proxy_token=proxy_token
            )
            logger.info(
                "recon served by mercury (%s) in %dms",
                profile.model_id,
                result.elapsed_ms,
            )
            return result
        except MercuryUnavailable as e:
            logger.warning(
                "mercury recon unavailable (%s); falling back to Claude recon", e
            )
            # fall through to the Claude path below, recording the failure cause

    # Claude recon path: either the resolved executor is Claude, or Mercury was
    # unavailable and we fell back. The orchestrator supplies the actual Claude
    # call; when none is supplied (library/test use) we return a structured
    # not-run result rather than raising, so a missing wiring degrades loudly but
    # safely.
    start = time.monotonic()
    if claude_recon is None:
        return ReconFindings(
            question=question,
            findings="",
            executor="claude",
            model_id=CLAUDE_MODEL_ID,
            elapsed_ms=0,
            ok=False,
            error="no claude_recon callable supplied",
        )
    findings = claude_recon(question)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return ReconFindings(
        question=question,
        findings=findings,
        executor="claude",
        model_id=CLAUDE_MODEL_ID,
        elapsed_ms=elapsed_ms,
        ok=True,
    )


def record_recon(state, findings: ReconFindings) -> None:
    """Write the recon telemetry onto ``state.last_recon`` (the
    ``time_to_verified_result`` hook). Imported lazily to keep executor.py a leaf
    that ``state.py`` could import without a cycle. Logged only, never a gate
    input. No-ops if ``state`` lacks the field (older state schema)."""
    from orchestrator.state import ReconRecord

    if not hasattr(state, "last_recon"):
        return
    state.last_recon = ReconRecord(
        executor=findings.executor,
        model_id=findings.model_id,
        elapsed_ms=findings.elapsed_ms,
        ok=findings.ok,
    )
