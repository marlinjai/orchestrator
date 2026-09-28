"""Per-role executor profiles and the one non-Anthropic executor path (Mercury recon).

This is the Wave-2 "per-role model routing" SEAM, deliberately the smallest
slice that the rest of the multi-model plan flips on. It is NOT a model registry
and NOT a set of provider adapters (the roadmap's named #1 scope-creep risk).

Two pieces:

1. ``ExecutorProfile`` + ``resolve_executor(role)``: an operator-owned mapping
   from a ROLE (``worker`` / ``recon`` / ``planner`` / ...) to a model +
   provider + auth mode. Config lives in
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
the Mercury path uses the secrets proxy's PROVIDER FORWARD
(``POST /forward/inception/chat/completions``): the orchestrator sends only the
chat request body; the proxy fetches ``INCEPTION_API_KEY`` from Infisical,
calls Inception itself and returns the completion verbatim. Which upstream and
which key location are fixed in the proxy's allowlist, never named by this
process. The key never enters the orchestrator process env or the transcript;
only the completion text crosses the wire. (An earlier design POSTed a shell
command to a ``/raw`` endpoint; the proxy refuses that by design, because an
unredacted shell endpoint would hand out every injected secret.) The transport is a small injectable
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
from typing import Callable, Literal, get_args

from orchestrator.proxy_token import resolve_proxy_token
from orchestrator.worker import AuthMode

logger = logging.getLogger(__name__)


# The providers an executor profile may name. Explicit, validated at load:
# provider is NEVER inferred from model-id string patterns (a "mercury-coder-2"
# release or an Anthropic id-shape change must not silently reroute a role).
Provider = Literal["anthropic", "inception"]

# reasoning_effort values the Inception API accepts (OpenAPI spec). Only valid
# with provider = "inception"; Anthropic profiles reject it at load.
REASONING_EFFORTS: tuple[str, ...] = ("instant", "low", "medium", "high")


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
MERCURY_MODEL_ID = "mercury-2"

# The secrets-proxy provider-forward route for Inception chat completions. The
# proxy owns the upstream URL and the key's Infisical location; this process
# only names the route.
INCEPTION_FORWARD_ROUTE = "/forward/inception/chat/completions"

# Chat-completions forward route per non-Anthropic provider (a literal table,
# not a registry). A provider missing here has no transport and is refused at
# startup.
PROVIDER_FORWARD_ROUTES: dict[str, str] = {"inception": INCEPTION_FORWARD_ROUTE}

# The secrets-proxy coordinates (same Tailscale-only host the Worker MCP +
# notify already use). The Mercury provider forward goes through this proxy so
# the Inception key is used server-side and never touches this process. The
# proxy token itself comes from ``proxy_token.resolve_proxy_token`` (0600 file
# first), never from a config literal.
PROXY_URL_ENV = "SECRETS_PROXY_URL"
DEFAULT_PROXY_URL = "http://100.124.97.31:8765"


def _config_home() -> Path:
    override = os.environ.get("ORCHESTRATOR_CONFIG_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "orchestrator"


@dataclass(frozen=True)
class ExecutorProfile:
    """Which model, provider and auth a given ROLE runs on.

    ``role`` is the routing key (``worker`` / ``recon`` / ``planner`` / ...).
    ``model_id`` is the model string. ``auth_mode`` reuses the Worker's existing
    ``AuthMode`` (``subscription`` keeps Claude on the flat login; ``api_key``
    bills the metered API -- the same load-bearing billing switch). Dollar
    ceilings are run-level (``--max-cost-usd``), not per role.

    ``is_claude`` is the judge-path invariant: the Worker and both Proxies must
    keep running Claude (their integrity is the whole trust model), so callers
    assert ``resolve_executor(<judge role>).is_claude``.
    """

    role: str
    model_id: str
    auth_mode: AuthMode = "subscription"
    provider: Provider = "anthropic"
    reasoning_effort: str | None = None

    @property
    def is_claude(self) -> bool:
        return self.provider == "anthropic" and self.model_id == CLAUDE_MODEL_ID

    @property
    def is_mercury(self) -> bool:
        return self.provider == "inception"


def _claude_profile(role: str) -> ExecutorProfile:
    """The default profile for any role: Claude on subscription auth.
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

    if "cost_ceiling_usd" in raw:
        # Removed in E3: a per-role ceiling was parsed but never enforced, and
        # dead safety-looking config is worse than none. Rejected loudly so an
        # operator who set it does not believe a ceiling is protecting them.
        raise ValueError(
            f"executor[{role}].cost_ceiling_usd is no longer supported (it was never "
            "enforced); use the run-level `orchestrator start --max-cost-usd` cap"
        )

    model_id = model_id.strip()

    provider = raw.get("provider")
    if provider is None:
        # Explicit-provider rule: only the default Claude model may omit it.
        # Anything else must name its provider so routing is never inferred
        # from model-id string shapes.
        if model_id != CLAUDE_MODEL_ID:
            raise ValueError(
                f"executor[{role}].provider is required for non-default model "
                f"{model_id!r} (one of {get_args(Provider)}); provider is never "
                "inferred from the model id"
            )
        provider = "anthropic"
    if provider not in get_args(Provider):
        raise ValueError(
            f"executor[{role}].provider must be one of {get_args(Provider)}, got {provider!r}"
        )
    if provider == "inception" and "model_id" not in raw:
        # The default model id is a Claude id; sending it to Inception would
        # fail at call time and silently fall back to Claude recon.
        raise ValueError(
            f"executor[{role}].model_id is required for provider 'inception' "
            "(the default is a Claude model id)"
        )

    effort = raw.get("reasoning_effort")
    if effort is not None:
        if provider != "inception":
            raise ValueError(
                f"executor[{role}].reasoning_effort is an Inception-only knob; "
                f"remove it for provider {provider!r}"
            )
        if effort not in REASONING_EFFORTS:
            raise ValueError(
                f"executor[{role}].reasoning_effort must be one of {REASONING_EFFORTS}, "
                f"got {effort!r}"
            )

    return ExecutorProfile(
        role=role,
        model_id=model_id,
        auth_mode=auth_mode,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        reasoning_effort=effort,
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
# Inception chat-completions call and returns the completion JSON verbatim. The
# production transport (``_proxy_provider_forward``) has the proxy use the
# Inception key server-side; tests inject a fake. Keeping this injectable is what
# lets the orchestrator NEVER hold the key while still getting a usable answer.
MercuryTransport = Callable[[str, str, dict], str]


def _proxy_provider_forward(proxy_url: str, token: str, request_body: dict) -> str:
    """Production transport: POST the chat request body to the proxy's
    provider forward and return the completion JSON verbatim.

    The proxy resolves the Inception key from its own allowlisted location and
    places it only in its outbound request, so nothing but the request body and
    the completion crosses this boundary. An HTTP error (the proxy's generic 502
    when it cannot resolve the key, or Inception's own 4xx/5xx passed through)
    raises ``MercuryUnavailable`` with the status and a short body excerpt, so
    the caller fails loud and falls back to Claude.
    """
    req = urllib.request.Request(
        f"{proxy_url}{INCEPTION_FORWARD_ROUTE}",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Proxy-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:300]
        except OSError:
            detail = ""
        raise MercuryUnavailable(
            f"secrets-proxy provider forward answered HTTP {e.code}: {detail}"
        ) from e
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise MercuryUnavailable(f"secrets-proxy provider forward failed: {e}") from e


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

    The Inception key is used SERVER-SIDE by the transport (default
    ``_proxy_provider_forward``); the orchestrator never holds it. If the proxy token
    is absent or the proxy/Inception call fails, this raises ``MercuryUnavailable``
    so the caller falls back to Claude recon. ``elapsed_ms`` + ``executor`` are
    recorded for the ``time_to_verified_result`` comparison (logged, never gated).
    """
    token = proxy_token if proxy_token is not None else resolve_proxy_token()
    if not token:
        raise MercuryUnavailable(
            "secrets-proxy token absent (~/.config/secrets-proxy/token or "
            "SECRETS_PROXY_TOKEN); cannot reach the provider forward"
        )
    url = (
        proxy_url
        if proxy_url is not None
        else os.environ.get(PROXY_URL_ENV, DEFAULT_PROXY_URL)
    ).rstrip("/")
    forward = transport or _proxy_provider_forward

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
    if profile.reasoning_effort is not None:
        request_body["reasoning_effort"] = profile.reasoning_effort

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


_EXECUTOR_PROVIDER = {"claude": "anthropic", "mercury": "inception"}
_PROVIDER_EXECUTOR = {v: k for k, v in _EXECUTOR_PROVIDER.items()}


def executor_label(profile: ExecutorProfile) -> str:
    """The short executor name telemetry records (``claude`` / ``mercury``),
    derived from the profile's explicit provider, never from the model id."""
    return _PROVIDER_EXECUTOR[profile.provider]


def record_recon(state, findings: ReconFindings) -> None:
    """Write the recon telemetry onto ``state`` as an ``ExecutorRecord`` (the
    ``time_to_verified_result`` hook): appended to ``state.executor_records``
    and pointed at by ``state.last_recon``. Imported lazily to keep executor.py
    a leaf that ``state.py`` could import without a cycle. Logged only, never a
    gate input.

    A Mercury recon is exactly one HTTP request, so it carries one call whose
    ``response_ms`` is the full round trip (secrets-proxy transit included; the
    non-streaming forward cannot split TTFT from generation). A Claude recon is
    an SDK query of unknown call count, so it carries no per-call rows rather
    than a fabricated one.
    """
    from orchestrator.state import CallLatency, ExecutorRecord

    calls = (
        [CallLatency(response_ms=findings.elapsed_ms)] if findings.executor == "mercury" else []
    )
    record = ExecutorRecord.build(
        role="recon",
        executor=findings.executor,
        provider=_EXECUTOR_PROVIDER.get(findings.executor, "anthropic"),
        model_id=findings.model_id,
        elapsed_ms=findings.elapsed_ms,
        ok=findings.ok,
        findings=findings.findings,
        iteration=getattr(state, "iteration", None),
        calls=calls,
    )
    state.executor_records.append(record)
    state.last_recon = record
