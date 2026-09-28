"""Where the orchestrator reads the secrets-proxy token from.

The token's home is a 0600 file, not the environment. An env-carried token gets
passed onward into child-process configs, and one such path put it in argv where
`ps` exposed it (see worker.py). The file is the single source of truth, so a
stale env value left over from before a rotation cannot win. Every caller of the
proxy in this process (notifications, the Mercury provider forward) resolves the
token here, so they cannot drift apart.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

PROXY_TOKEN_ENV = "SECRETS_PROXY_TOKEN"
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "secrets-proxy" / "token"
TOKEN_FILE_ENV = "SECRETS_PROXY_TOKEN_FILE"


def resolve_proxy_token() -> str | None:
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
