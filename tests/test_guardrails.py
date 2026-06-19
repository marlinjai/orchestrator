import re
import time
from pathlib import Path

import pytest

from orchestrator.guardrails import (
    DENIED_BASH_PATTERNS,
    bash_allowed,
    cost_cap_hit,
    cumulative_tokens,
    estimate_cost_usd,
    iteration_cap_hit,
    kill_switch_active,
    usage_cap_hit,
    wall_clock_cap_hit,
)
from orchestrator.state import IterationUsage


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
        "infisical run -- pnpm migrate",
        "infisical run --env=dev -- node script.js",
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


def test_estimate_cost_usd_known_model():
    # 1M input + 1M output on sonnet pricing (3 / 15 per Mtok) = 18.0
    usage = [
        IterationUsage(
            iteration=1,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="claude-sonnet-4-6",
        )
    ]
    assert estimate_cost_usd(usage) == pytest.approx(18.0)


def test_estimate_cost_usd_opus_with_cache():
    # opus: input 15, output 75, cache_read 1.5 per Mtok
    usage = [
        IterationUsage(
            iteration=1,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            model="claude-opus-4-8",
        )
    ]
    assert estimate_cost_usd(usage) == pytest.approx(15.0 + 75.0 + 1.5)


def test_estimate_cost_usd_unknown_model_uses_default():
    usage = [IterationUsage(iteration=1, input_tokens=1_000_000, model="mystery-model")]
    # default pricing input = 3.0 per Mtok
    assert estimate_cost_usd(usage) == pytest.approx(3.0)


def test_estimate_cost_usd_empty():
    assert estimate_cost_usd([]) == 0.0


def test_cost_cap_hit():
    assert not cost_cap_hit(estimate_usd=5.0, max_usd=None)
    assert not cost_cap_hit(estimate_usd=5.0, max_usd=0)
    assert not cost_cap_hit(estimate_usd=4.99, max_usd=5.0)
    assert cost_cap_hit(estimate_usd=5.0, max_usd=5.0)
    assert cost_cap_hit(estimate_usd=6.0, max_usd=5.0)


def test_cumulative_tokens_sums_all_legs():
    usage = [
        IterationUsage(
            iteration=1,
            input_tokens=100,
            output_tokens=10,
            cache_read_tokens=1000,
            cache_creation_tokens=50,
        ),
        IterationUsage(iteration=2, input_tokens=200, output_tokens=20),
    ]
    assert cumulative_tokens(usage) == 100 + 10 + 1000 + 50 + 200 + 20


def test_cumulative_tokens_empty():
    assert cumulative_tokens([]) == 0


def test_usage_cap_hit():
    assert not usage_cap_hit(total_tokens=500, max_tokens=None)
    assert not usage_cap_hit(total_tokens=500, max_tokens=0)
    assert not usage_cap_hit(total_tokens=499, max_tokens=500)
    assert usage_cap_hit(total_tokens=500, max_tokens=500)
    assert usage_cap_hit(total_tokens=501, max_tokens=500)
