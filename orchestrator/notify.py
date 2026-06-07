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
import shutil
import subprocess
import urllib.request

logger = logging.getLogger(__name__)

NOTIFY_URL_ENV = "ORCHESTRATOR_NOTIFY_URL"
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "escalated", "stopped", "failed"})
_MAX_MESSAGE = 240


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
