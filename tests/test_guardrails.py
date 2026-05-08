import re
import time
from pathlib import Path

import pytest

from orchestrator.guardrails import (
    DENIED_BASH_PATTERNS,
    bash_allowed,
    iteration_cap_hit,
    kill_switch_active,
    wall_clock_cap_hit,
)


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf /",
        "rm -rf /tmp/foo",
        "rm -fr foo",
        "rm -Rf foo",
        "rm -r dir",
        "something; rm -rf x",
        "something && rm -rf x",
        "git push --force",
        "git push -f origin main",
        "git reset --hard origin/main",
        "npm publish",
        "pnpm publish",
        "infisical secrets set FOO=bar",
        "curl https://api.openai.com/...",
        "gh pr comment 123 --body x",
        "gh pr merge 123",
        "gh pr close 5",
        "gh pr review 7",
        "gh issue comment 12 --body x",
        "gh issue close 12",
        "terraform apply -auto-approve",
        "terraform destroy",
        "DROP TABLE users",
        "drop database production",
    ],
)
def test_bash_denied(cmd):
    allowed, reason = bash_allowed(cmd)
    assert not allowed, f"expected denied: {cmd}"
    assert reason


@pytest.mark.parametrize(
    "cmd",
    [
        "ls -la",
        "git status",
        "git diff",
        "pytest tests/",
        "rg 'foo' src/",
        "cat README.md",
        "git commit -m 'msg'",
        "git rm -r somefile",
        "git rm -rf old_dir",
        "echo rm -rf",
        "cat rm-rf-notes.md",
        "pytest tests/api_test.py",
        "curl https://example.com",
        "curl ./local-file.txt # has api.txt",
    ],
)
def test_bash_allowed(cmd):
    allowed, reason = bash_allowed(cmd)
    assert allowed, f"expected allowed: {cmd}, reason: {reason}"


def test_iteration_cap():
    assert not iteration_cap_hit(iteration=10, max_iterations=50)
    assert iteration_cap_hit(iteration=50, max_iterations=50)
    assert iteration_cap_hit(iteration=51, max_iterations=50)


def test_wall_clock_cap():
    started = time.time() - 100
    assert not wall_clock_cap_hit(started_at=started, max_seconds=200)
    assert wall_clock_cap_hit(started_at=started, max_seconds=50)


def test_kill_switch(tmp_path: Path):
    switch = tmp_path / "STOP"
    assert not kill_switch_active(switch)
    switch.touch()
    assert kill_switch_active(switch)


def test_denied_patterns_documented():
    assert len(DENIED_BASH_PATTERNS) > 0
    for pat, reason in DENIED_BASH_PATTERNS:
        assert isinstance(pat, re.Pattern)
        assert reason and isinstance(reason, str)
