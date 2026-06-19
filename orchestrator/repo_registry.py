"""Operator-owned repo registry (the trust anchor's data layer).

The verify gate runs the goal's own command in the Worker's tree, so a green
build is only as trustworthy as the tests in that tree. The real fix (the
held-out verifier) needs a test set the Worker cannot reach, plus a per-repo
stakes tier and an allowlist of MCP servers. The red-team's headline finding:
NONE of those security-relevant fields may come from the goal file, because the
goal file is renegotiable DATA a Worker (or a future auto-scaffolder) can author.
They must come from an OPERATOR-owned registry keyed by the one thing a Worker
cannot fake: the project's real git remote.

This module is that registry. It lives OUTSIDE any repo a Worker touches
(default ``~/.config/orchestrator/repos.toml``, override with
``ORCHESTRATOR_REPOS_CONFIG``), is keyed by the normalized git remote
(``host/owner/repo``, lowercased), and a goal file can at most BE in a registered
repo: it can never set these fields. A project with no entry resolves to a
permissive default (no held-out verify, stakes unknown) so existing runs keep
working while the registry fills in. A malformed registry fails loud, never
silently drops a security field.
"""

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from orchestrator.guardrails import bash_allowed


# Stakes tiers mirror the roadmap autonomy ladder: 1 read-only, 2 reversible,
# 3 external, 4 irreversible. Higher = more caution before acting on this repo.
VALID_STAKES_TIERS: tuple[int, ...] = (1, 2, 3, 4)


@dataclass
class RepoPolicy:
    remote: str | None = None            # normalized git remote (machine-computed)
    held_out_verify: str | None = None   # command for the out-of-reach test set
    stakes_tier: int | None = None       # 1 read-only .. 4 irreversible
    allowed_mcp_servers: list[str] | None = None
    source: str = "default"              # "registry" when matched, else "default"


def _registry_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    override = os.environ.get("ORCHESTRATOR_REPOS_CONFIG")
    if override:
        return Path(override).expanduser()
    home = os.environ.get("ORCHESTRATOR_CONFIG_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".config" / "orchestrator"
    return base / "repos.toml"


def normalize_remote(url: str | None) -> str | None:
    """Canonicalize a git remote URL to ``host/path`` (lowercased, no .git, no creds).

    Maps all of ``git@host:owner/repo.git``, ``https://host/owner/repo.git``,
    ``ssh://git@host/owner/repo``, and ``https://user:tok@host/owner/repo.git`` to
    the same key, so the registry is keyed by identity, not by URL spelling. An
    already-normalized key (``host/owner/repo``) passes through unchanged.
    """
    if not url:
        return None
    text = url.strip()
    if not text:
        return None
    # scp-like syntax: [user@]host:path (no scheme, a colon before any slash)
    scp = re.match(r"^[^/@]+@([^/:]+):(.+)$", text)
    if scp:
        host, path = scp.group(1), scp.group(2)
    else:
        scheme = re.match(r"^[a-zA-Z][\w+.-]*://(.+)$", text)
        rest = scheme.group(1) if scheme else text
        rest = re.sub(r"^[^@/]*@", "", rest)  # strip userinfo (user:tok@)
        host, sep, path = rest.partition("/")
        if not sep:
            path = ""
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    key = f"{host}/{path}".strip("/").lower()
    return key or None


def git_remote_url(project_dir: Path, remote: str = "origin") -> str | None:
    """Return the configured URL of ``remote`` for ``project_dir``, or None.

    None when the dir is not a git repo or the remote is unset: the caller then
    falls back to the default (no-registry) policy.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def _policy_from_entry(key: str, entry: dict, cfg_path: Path) -> RepoPolicy:
    held = entry.get("held_out_verify")
    if held is not None:
        if not isinstance(held, str) or not held.strip():
            raise ValueError(
                f"held_out_verify for {key!r} must be a non-empty string in {cfg_path}"
            )
        held = held.strip()
        allowed, reason = bash_allowed(held)
        if not allowed:
            raise ValueError(
                f"held_out_verify for {key!r} hits the bash denylist ({reason}) in {cfg_path}"
            )

    tier = entry.get("stakes_tier")
    if tier is not None and tier not in VALID_STAKES_TIERS:
        raise ValueError(
            f"stakes_tier for {key!r} must be one of {VALID_STAKES_TIERS} in {cfg_path}"
        )

    servers = entry.get("allowed_mcp_servers")
    if servers is not None and (
        not isinstance(servers, list) or not all(isinstance(s, str) for s in servers)
    ):
        raise ValueError(
            f"allowed_mcp_servers for {key!r} must be a list of strings in {cfg_path}"
        )

    return RepoPolicy(
        remote=key,
        held_out_verify=held,
        stakes_tier=tier,
        allowed_mcp_servers=servers,
        source="registry",
    )


def load_repo_registry(path: Path | None = None) -> dict[str, RepoPolicy]:
    """Load the operator registry into ``{normalized_remote: RepoPolicy}``.

    Returns ``{}`` when the file is absent (registry is opt-in). Raises
    ValueError on any malformed table or field, so a typo in a security-relevant
    field fails loud rather than silently disarming a gate.
    """
    cfg_path = _registry_path(path)
    if not cfg_path.exists():
        return {}
    try:
        data = tomllib.loads(cfg_path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"repo registry malformed: {cfg_path}: {e}") from e

    repos = data.get("repos", {})
    if not isinstance(repos, dict):
        raise ValueError(f"[repos] must be a table in {cfg_path}")

    out: dict[str, RepoPolicy] = {}
    for raw_key, entry in repos.items():
        if not isinstance(entry, dict):
            raise ValueError(f"repo entry {raw_key!r} must be a table in {cfg_path}")
        key = normalize_remote(raw_key)
        if not key:
            raise ValueError(f"repo key {raw_key!r} is not a valid remote in {cfg_path}")
        out[key] = _policy_from_entry(key, entry, cfg_path)
    return out


def resolve_repo_policy(project_dir: Path, registry_path: Path | None = None) -> RepoPolicy:
    """Resolve the operator policy for ``project_dir`` by its real git remote.

    The remote is machine-computed (``git remote get-url``), so a goal file
    cannot point the lookup at a softer entry. No matching entry yields a default
    policy that still carries the computed remote (for visibility) but no
    held-out verify or stakes tier.
    """
    remote = normalize_remote(git_remote_url(project_dir))
    registry = load_repo_registry(registry_path)
    if remote and remote in registry:
        return registry[remote]
    return RepoPolicy(remote=remote, source="default")
