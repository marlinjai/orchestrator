"""Terminal-state notifications for orchestrator runs.

Detached runs (`nohup orchestrator start ... &`) reach a terminal state and
nothing tells the operator, so the follow-up (review, merge, dispatch next)
stalls until someone happens to poll. This module pings on every terminal state.

Fire-and-forget and fail-safe: a notification failure must NEVER affect the run.
Two best-effort channels, both optional:

  1. macOS desktop banner + sound, when running on Darwin and `osascript` exists.
     Covers the "I'm at my machine in a batch and didn't notice it finished" case.
  2. a webhook POST to ORCHESTRATOR_NOTIFY_URL (or the `webhook_url` arg), if set.
     Covers "away from the machine": point it at an ntfy topic, Pushover, a Slack
     incoming webhook, or any endpoint that accepts a POST. The body is JSON; ntfy
     also reads the `Title` header, which we set.

This is the "ping the human" path. The complementary "wake the session that
dispatched the run" path is achieved by launching the run as a harness-tracked
background task (the Bash tool's background mode) instead of `nohup`, so the
Claude Code session is re-invoked on exit; see the autonomous-orchestration skill.
"""

import json
import logging
import os
import platform
import shlex
import shutil
import subprocess
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

NOTIFY_URL_ENV = "ORCHESTRATOR_NOTIFY_URL"
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "escalated", "stopped", "failed"})
_MAX_MESSAGE = 240

# Telegram via the secrets-proxy: the bot token + chat id stay in Infisical and
# are injected server-side, so they never enter this process env or any caller
# context. Active when SECRETS_PROXY_TOKEN is present (the orchestrator already
# carries it for the Worker's secrets-proxy MCP). The Infisical coordinates
# default to the monitoring path and are env-overridable.
PROXY_URL_ENV = "SECRETS_PROXY_URL"
PROXY_TOKEN_ENV = "SECRETS_PROXY_TOKEN"
DEFAULT_PROXY_URL = "http://100.124.97.31:8765"
# The proxy token's home is a 0600 file, not the environment. An env-carried
# token gets passed onward into child-process configs, and one such path put it
# in argv where `ps` exposed it (see worker.py). The file is the single source of
# truth, so a stale env value left over from before a rotation cannot win.
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "secrets-proxy" / "token"
TOKEN_FILE_ENV = "SECRETS_PROXY_TOKEN_FILE"
TELEGRAM_PROJECT_ID = os.environ.get(
    "ORCHESTRATOR_TELEGRAM_PROJECT_ID", "6adabd49-59d3-4bab-8a1e-c104a0da3c64"
)
TELEGRAM_SECRET_PATH = os.environ.get("ORCHESTRATOR_TELEGRAM_PATH", "/monitoring")
TELEGRAM_SECRET_ENV = os.environ.get("ORCHESTRATOR_TELEGRAM_ENV", "production")


def _macos_notification(title: str, message: str) -> None:
    if platform.system() != "Darwin":
        return
    osascript = shutil.which("osascript")
    if not osascript:
        return
    # Pass the script via argv (osascript -e). Strip double quotes so the literal
    # cannot break out of the AppleScript string; this is a banner, not a shell.
    safe_title = title.replace('"', "'")
    safe_msg = message.replace('"', "'")
    script = (
        f'display notification "{safe_msg}" with title "{safe_title}" sound name "Glass"'
    )
    subprocess.run(
        [osascript, "-e", script], check=False, timeout=10, capture_output=True
    )


def _webhook(url: str, title: str, message: str, status: str) -> None:
    payload = json.dumps(
        {"title": title, "message": message, "status": status}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            # ntfy honors these; harmless to other endpoints.
            "Title": title,
            "X-Title": title,
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10).close()


def _resolve_proxy_token() -> str | None:
    """Resolve the secrets-proxy token: 0600 file first, env var as fallback.

    Mirrors the MCP server's `resolveProxyToken()` so both sides read the same
    single source of truth. A token file readable by group/other is refused
    rather than trusted; a missing file falls back to the env var so a
    containerized caller with no writable home still works.
    """
    token_file = Path(os.environ.get(TOKEN_FILE_ENV) or DEFAULT_TOKEN_FILE)
    try:
        if token_file.stat().st_mode & 0o077:
            logger.warning(
                "secrets-proxy token file %s is readable by group/other; ignoring it",
                token_file,
            )
        else:
            token = token_file.read_text(encoding="utf-8").strip()
            if token:
                return token
    except OSError:
        pass
    return os.environ.get(PROXY_TOKEN_ENV) or None


def _telegram_via_proxy(title: str, message: str) -> None:
    """Send a Telegram message through the secrets-proxy.

    The proxy injects TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID server-side from
    Infisical, so the bot credentials never enter this process env or any
    caller's context. Reuses the proxy token the orchestrator already holds for
    the Worker's secrets-proxy MCP; skips silently when that token is absent.
    """
    token = _resolve_proxy_token()
    if not token:
        return
    proxy_url = os.environ.get(PROXY_URL_ENV, DEFAULT_PROXY_URL).rstrip("/")
    text = f"{title}\n{message}"
    # The message is untrusted (it carries the run's exit reason), so it is
    # shell-single-quoted via shlex.quote. The $TELEGRAM_* refs are static and
    # expand from the proxy-injected env, never from the message.
    curl = (
        'curl -s -X POST '
        '"https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" '
        '--data-urlencode "chat_id=$TELEGRAM_CHAT_ID" '
        f'--data-urlencode {shlex.quote("text=" + text)}'
    )
    body = json.dumps(
        {
            "command": curl,
            "workingDir": "/tmp",
            "env": TELEGRAM_SECRET_ENV,
            "projectId": TELEGRAM_PROJECT_ID,
            "path": TELEGRAM_SECRET_PATH,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{proxy_url}/execute",
        data=body,
        headers={"Content-Type": "application/json", "X-Proxy-Token": token},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15).close()


def notify(
    *, task_id: str, status: str, reason: str = "", webhook_url: str | None = None
) -> None:
    """Best-effort notify on a terminal orchestrator state. Never raises.

    `webhook_url` overrides the ORCHESTRATOR_NOTIFY_URL env var when given.
    """
    title = f"orchestrator: {task_id} {status}"
    message = (reason or status).strip()
    if len(message) > _MAX_MESSAGE:
        message = message[: _MAX_MESSAGE - 3] + "..."

    try:
        _macos_notification(title, message)
    except Exception as e:  # pragma: no cover - best-effort
        logger.debug("macos notification failed: %s", e)

    url = webhook_url if webhook_url is not None else os.environ.get(NOTIFY_URL_ENV)
    if url:
        try:
            _webhook(url, title, message, status)
        except Exception as e:  # pragma: no cover - best-effort
            logger.debug("webhook notify failed: %s", e)

    try:
        _telegram_via_proxy(title, message)
    except Exception as e:  # pragma: no cover - best-effort
        logger.debug("telegram notify failed: %s", e)
