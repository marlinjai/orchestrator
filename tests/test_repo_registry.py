import subprocess
from pathlib import Path

import pytest

from orchestrator.repo_registry import (
    RepoPolicy,
    git_remote_url,
    load_repo_registry,
    normalize_remote,
    resolve_repo_policy,
)


# --- normalize_remote ---

@pytest.mark.parametrize(
    "url,expected",
    [
        ("git@github.com:marlinjai/orchestrator.git", "github.com/marlinjai/orchestrator"),
        ("https://github.com/marlinjai/orchestrator.git", "github.com/marlinjai/orchestrator"),
        ("https://github.com/marlinjai/orchestrator", "github.com/marlinjai/orchestrator"),
        ("ssh://git@github.com/marlinjai/orchestrator.git", "github.com/marlinjai/orchestrator"),
        ("https://user:tok@github.com/marlinjai/orchestrator.git", "github.com/marlinjai/orchestrator"),
        ("https://GitHub.com/Marlinjai/Orchestrator.git", "github.com/marlinjai/orchestrator"),
        # already-normalized key passes through
        ("github.com/marlinjai/orchestrator", "github.com/marlinjai/orchestrator"),
        # nested groups (gitlab style)
        ("git@gitlab.com:group/sub/repo.git", "gitlab.com/group/sub/repo"),
    ],
)
def test_normalize_remote_canonicalizes(url, expected):
    assert normalize_remote(url) == expected


def test_normalize_remote_empty_and_none():
    assert normalize_remote(None) is None
    assert normalize_remote("") is None
    assert normalize_remote("   ") is None


def test_normalize_remote_is_idempotent():
    once = normalize_remote("git@github.com:marlinjai/orchestrator.git")
    assert normalize_remote(once) == once


# --- git_remote_url (real git repo) ---

def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "t@example.com"], repo)
    _run(["git", "config", "user.name", "T"], repo)
    return repo


def test_git_remote_url_returns_origin(git_repo: Path):
    _run(["git", "remote", "add", "origin", "git@github.com:test/x.git"], git_repo)
    assert git_remote_url(git_repo) == "git@github.com:test/x.git"


def test_git_remote_url_none_without_remote(git_repo: Path):
    assert git_remote_url(git_repo) is None


def test_git_remote_url_none_outside_repo(tmp_path: Path):
    assert git_remote_url(tmp_path) is None


# --- load_repo_registry ---

def _write(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_load_registry_missing_file_is_empty(tmp_path: Path):
    assert load_repo_registry(tmp_path / "nope.toml") == {}


def test_load_registry_parses_and_normalizes_keys(tmp_path: Path):
    reg = _write(
        tmp_path / "repos.toml",
        """
[repos."git@github.com:marlinjai/Orchestrator.git"]
held_out_verify = "pytest -q /opt/heldout/orch"
stakes_tier = 4
allowed_mcp_servers = ["orchestrator-state", "secrets-proxy"]
""",
    )
    registry = load_repo_registry(reg)
    assert "github.com/marlinjai/orchestrator" in registry
    pol = registry["github.com/marlinjai/orchestrator"]
    assert pol.held_out_verify == "pytest -q /opt/heldout/orch"
    assert pol.stakes_tier == 4
    assert pol.allowed_mcp_servers == ["orchestrator-state", "secrets-proxy"]
    assert pol.source == "registry"


def test_load_registry_rejects_malformed_toml(tmp_path: Path):
    reg = _write(tmp_path / "repos.toml", "[repos.\nbroken")
    with pytest.raises(ValueError):
        load_repo_registry(reg)


def test_load_registry_rejects_bad_stakes_tier(tmp_path: Path):
    reg = _write(
        tmp_path / "repos.toml",
        '[repos."github.com/a/b"]\nstakes_tier = 9\n',
    )
    with pytest.raises(ValueError):
        load_repo_registry(reg)


def test_load_registry_rejects_denylisted_held_out_verify(tmp_path: Path):
    reg = _write(
        tmp_path / "repos.toml",
        '[repos."github.com/a/b"]\nheld_out_verify = "gh pr merge 1"\n',
    )
    with pytest.raises(ValueError):
        load_repo_registry(reg)


def test_load_registry_rejects_non_list_servers(tmp_path: Path):
    reg = _write(
        tmp_path / "repos.toml",
        '[repos."github.com/a/b"]\nallowed_mcp_servers = "secrets-proxy"\n',
    )
    with pytest.raises(ValueError):
        load_repo_registry(reg)


# --- resolve_repo_policy ---

def test_resolve_matches_registry_by_remote(tmp_path: Path, git_repo: Path):
    _run(["git", "remote", "add", "origin", "https://github.com/marlinjai/orchestrator.git"], git_repo)
    reg = _write(
        tmp_path / "repos.toml",
        '[repos."github.com/marlinjai/orchestrator"]\n'
        'held_out_verify = "pytest -q"\nstakes_tier = 4\n',
    )
    pol = resolve_repo_policy(git_repo, reg)
    assert pol.source == "registry"
    assert pol.remote == "github.com/marlinjai/orchestrator"
    assert pol.held_out_verify == "pytest -q"
    assert pol.stakes_tier == 4


def test_resolve_default_when_remote_not_registered(tmp_path: Path, git_repo: Path):
    _run(["git", "remote", "add", "origin", "git@github.com:someone/other.git"], git_repo)
    reg = _write(
        tmp_path / "repos.toml",
        '[repos."github.com/marlinjai/orchestrator"]\nstakes_tier = 4\n',
    )
    pol = resolve_repo_policy(git_repo, reg)
    assert pol == RepoPolicy(remote="github.com/someone/other", source="default")
    assert pol.held_out_verify is None
    assert pol.stakes_tier is None


def test_resolve_default_when_no_remote(tmp_path: Path, git_repo: Path):
    pol = resolve_repo_policy(git_repo, tmp_path / "absent.toml")
    assert pol.source == "default"
    assert pol.remote is None
    assert pol.held_out_verify is None
