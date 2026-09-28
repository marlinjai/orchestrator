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
unredacted shell endpoint would hand out every injected secret.)

The forward itself goes through the ``secrets-proxy-call`` CLI
(``mcp/dist/cli.js forward``, shipped alongside the secrets-proxy MCP client),
not a direct HTTP call with a token: the CLI mints its own short-lived access
token from the operator's Infisical machine identity in the macOS Keychain, so
this process never holds a token, only the CLI's path. The transport is a
small injectable seam (``MercuryTransport``) so tests run with a fake and the
production default keeps the key and the token both server-side / in the CLI.
This composes with ``worker.apply_env_contract``'s foreign-key scrub rather
than fighting it: the orchestrator never holds the key or a token, so there is
nothing for the scrub to leak.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, get_args

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

# The secrets-proxy-call CLI (shipped alongside the secrets-proxy MCP client)
# is what actually reaches the proxy: it mints its own short-lived access
# token from the operator's Infisical machine identity in the macOS Keychain,
# so this process names only the CLI's path, never a proxy URL or a token.
PROXY_CLI_ENV = "SECRETS_PROXY_CLI"
DEFAULT_PROXY_CLI = Path.home() / "software-dev" / "secrets-proxy" / "mcp" / "dist" / "cli.js"


def resolve_proxy_cli() -> Path | None:
    """The secrets-proxy-call CLI path, or None when it is not built (no node
    on PATH, or the secrets-proxy repo not built on this machine)."""
    if not shutil.which("node"):
        return None
    cli = Path(os.environ.get(PROXY_CLI_ENV) or DEFAULT_PROXY_CLI)
    return cli if cli.is_file() else None


# Chat-completions forward route per non-Anthropic provider (a literal table,
# not a registry). A provider missing here has no transport and is refused at
# startup.
PROVIDER_FORWARD_ROUTES: dict[str, str] = {"inception": INCEPTION_FORWARD_ROUTE}

# Context window per provider (tokens). The session-refresh ("token watcher")
# threshold is a fraction of it, see handover_threshold.
DEFAULT_CONTEXT_WINDOWS: dict[str, int] = {"anthropic": 200_000, "inception": 128_000}
HANDOVER_WINDOW_FRACTION = 0.7


def handover_threshold(profile: "ExecutorProfile", configured: int) -> int:
    """The context size at which the Worker's session is handed over to a fresh
    one: the operator's ``context_handover_tokens`` capped at 70 percent of the
    Worker model's window (design section 6.3, the M9 token watcher). A
    non-positive configured value disables proactive handover (returns 0)."""
    if configured <= 0:
        return 0
    return min(configured, int(profile.context_window * HANDOVER_WINDOW_FRACTION))


# A per-run executor overlay, set by an OPERATOR process (the Agentic OS worker
# routes a tenant's `sprint` rule to the Worker model this way): its
# [executors.<role>] tables replace those of config.toml for the run, while
# config.toml's other sections and repos.toml (the held-out verifiers) stay in
# force. Environment, not goal frontmatter: a goal file can never set it.
EXECUTORS_FILE_ENV = "ORCHESTRATOR_EXECUTORS_FILE"


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
    # The model's context window in tokens; None means the provider default
    # (DEFAULT_CONTEXT_WINDOWS). Operator-overridable in [executors.<role>].
    context_window_tokens: int | None = None

    @property
    def context_window(self) -> int:
        return self.context_window_tokens or DEFAULT_CONTEXT_WINDOWS[self.provider]

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

    window = raw.get("context_window_tokens")
    if window is not None and (isinstance(window, bool) or not isinstance(window, int) or window < 1000):
        raise ValueError(
            f"executor[{role}].context_window_tokens must be an integer >= 1000, got {window!r}"
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
        context_window_tokens=window,
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
    profiles = _read_executors(cfg_path) if cfg_path.exists() else {}
    if path is None:
        overlay = os.environ.get(EXECUTORS_FILE_ENV)
        if overlay:
            overlay_path = Path(overlay).expanduser()
            if not overlay_path.exists():
                raise ValueError(f"{EXECUTORS_FILE_ENV} points at a missing file: {overlay_path}")
            profiles.update(_read_executors(overlay_path))
    return profiles


def _read_executors(cfg_path: Path) -> dict[str, ExecutorProfile]:
    try:
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
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
    """Raised when the Mercury path cannot run (the secrets-proxy-call CLI is
    missing, the forward failed, or the Inception response is malformed). The
    caller catches this and falls back to Claude recon: a loud failure, never a
    silent skip."""


# A transport takes the secrets-proxy-call CLI's path and the JSON request body
# for the Inception chat-completions call, and returns the completion JSON
# verbatim. The production transport (``_proxy_provider_forward``) shells out to
# the CLI, which mints its own token and has the proxy use the Inception key
# server-side; tests inject a fake. Keeping this injectable is what lets the
# orchestrator NEVER hold a key or a token while still getting a usable answer.
MercuryTransport = Callable[[str, dict], str]


def _proxy_provider_forward(cli_path: str, request_body: dict) -> str:
    """Production transport: pipe the chat request body into the
    secrets-proxy-call CLI's ``forward`` subcommand and return the completion
    JSON verbatim.

    The CLI mints its own short-lived Infisical access token from the
    operator's Keychain identity and the proxy resolves the Inception key from
    its own allowlisted location, so nothing but the request body and the
    completion crosses this process. A non-zero exit (the CLI could not reach
    the proxy, the proxy's generic 502 when it cannot resolve the key, or
    Inception's own 4xx/5xx passed through) raises ``MercuryUnavailable`` with
    the CLI's stderr reason, so the caller fails loud and falls back to Claude.
    """
    try:
        result = subprocess.run(
            ["node", cli_path, "forward", INCEPTION_FORWARD_ROUTE],
            input=json.dumps(request_body),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MercuryUnavailable(f"secrets-proxy-call forward failed to run: {e}") from e
    if result.returncode != 0:
        reason = (result.stderr or "").strip()[:300]
        raise MercuryUnavailable(
            f"secrets-proxy-call forward exited {result.returncode}: {reason}"
        )
    return result.stdout


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
    cli_path: str | None = None,
    max_tokens: int = 1024,
) -> ReconFindings:
    """Ask Mercury (Inception) a read-only reconnaissance question and return a
    structured ``ReconFindings``.

    Read-only by construction: this builds one chat-completions request and
    returns the answer text. It runs NO tools, writes NO files, touches NO repo.

    The Inception key is used SERVER-SIDE by the transport (default
    ``_proxy_provider_forward``, which shells out to the secrets-proxy-call
    CLI); the orchestrator never holds it, nor a proxy token. Availability is
    simply "the CLI exists": if it is missing or the forward/Inception call
    fails, this raises ``MercuryUnavailable`` so the caller falls back to
    Claude recon. ``elapsed_ms`` + ``executor`` are recorded for the
    ``time_to_verified_result`` comparison (logged, never gated).
    """
    resolved = cli_path if cli_path is not None else resolve_proxy_cli()
    if not resolved:
        raise MercuryUnavailable(
            f"secrets-proxy-call CLI not found (looked for ${PROXY_CLI_ENV} or "
            f"{DEFAULT_PROXY_CLI}); cannot reach the provider forward"
        )
    path = str(resolved)
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
    raw = forward(path, request_body)
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
    cli_path: str | None = None,
) -> ReconFindings:
    """Run a read-only reconnaissance question through the resolved ``recon``
    executor, falling back to Claude recon on any Mercury failure.

    This is the ONE real call site of the seam: it resolves ``recon`` (Claude by
    default), and ONLY when an operator config points it at Mercury does the
    non-Claude path run. A ``MercuryUnavailable`` (the secrets-proxy-call CLI is
    missing, the forward failed, or the Inception response is malformed) FAILS
    LOUD into a logged warning and a Claude recon fallback -- never a silent
    skip, never a blocked run.

    ``claude_recon`` is the Claude recon function (question -> findings text). It
    is injected so the orchestrator can wire its own Claude call (the Decision
    Proxy's own model) without this module importing the SDK. When the resolved
    executor is already Claude, it is used directly.
    """
    profile = resolve_executor("recon", config_path=config_path)

    if profile.is_mercury:
        try:
            result = run_mercury_recon(
                question, profile=profile, transport=transport, cli_path=cli_path
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
