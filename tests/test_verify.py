from pathlib import Path

from orchestrator.verify import (
    DEFAULT_FIX_CAP,
    DEFAULT_TIMEOUT_S,
    VerifyOutcome,
    decide_after_verify,
    load_verify_config,
    run_verify,
)


# ---- load_verify_config ----


def test_load_verify_config_absent():
    cfg = load_verify_config({})
    assert cfg.command is None
    assert cfg.fix_cap == DEFAULT_FIX_CAP
    assert cfg.timeout_s == DEFAULT_TIMEOUT_S


def test_load_verify_config_full():
    cfg = load_verify_config(
        {"verify": "pnpm test && pnpm build", "verify_fix_cap": "3", "verify_timeout_s": "600"}
    )
    assert cfg.command == "pnpm test && pnpm build"
    assert cfg.fix_cap == 3
    assert cfg.timeout_s == 600.0


def test_load_verify_config_blank_command_is_none():
    assert load_verify_config({"verify": "   "}).command is None


def test_load_verify_config_floors_fix_cap_at_one():
    assert load_verify_config({"verify": "true", "verify_fix_cap": "0"}).fix_cap == 1
    assert load_verify_config({"verify": "true", "verify_fix_cap": "0"}).fix_cap >= 1


def test_load_verify_config_bad_fix_cap_falls_back_to_default():
    assert load_verify_config({"verify": "true", "verify_fix_cap": "nope"}).fix_cap == DEFAULT_FIX_CAP


# ---- decide_after_verify (pure) ----


def _outcome(status: str, exit_code=0, tail="", command="true") -> VerifyOutcome:
    return VerifyOutcome(status=status, exit_code=exit_code, tail=tail, command=command)


def test_decide_pass_completes_and_resets_attempts():
    d = decide_after_verify(outcome=_outcome("pass"), prior_attempts=1, fix_cap=2)
    assert d.action == "complete"
    assert d.attempts == 0


def test_decide_misconfigured_escalates():
    d = decide_after_verify(
        outcome=_outcome("misconfigured", exit_code=None, tail="refused by denylist"),
        prior_attempts=0,
        fix_cap=2,
    )
    assert d.action == "escalate"
    assert "misconfigured" in (d.exit_reason or "")


def test_decide_fail_under_cap_retries_with_failure_in_message():
    d = decide_after_verify(
        outcome=_outcome("fail", exit_code=1, tail="boom the build broke"),
        prior_attempts=0,
        fix_cap=2,
    )
    assert d.action == "retry"
    assert d.attempts == 1
    assert d.next_message and "boom the build broke" in d.next_message


def test_decide_fail_at_cap_escalates():
    d = decide_after_verify(
        outcome=_outcome("fail", exit_code=1, tail="still broken"),
        prior_attempts=1,
        fix_cap=2,
    )
    assert d.action == "escalate"
    assert d.attempts == 2
    assert "failed 2x" in (d.exit_reason or "")


# ---- run_verify (real subprocess) ----


async def test_run_verify_pass(tmp_path: Path):
    out = await run_verify("exit 0", tmp_path, timeout_s=10)
    assert out.status == "pass"
    assert out.exit_code == 0


async def test_run_verify_fail_captures_merged_output(tmp_path: Path):
    out = await run_verify("echo boom >&2; exit 3", tmp_path, timeout_s=10)
    assert out.status == "fail"
    assert out.exit_code == 3
    assert "boom" in out.tail  # stderr is merged into stdout


async def test_run_verify_denylisted_command_is_misconfigured(tmp_path: Path):
    out = await run_verify("gh pr merge 1", tmp_path, timeout_s=10)
    assert out.status == "misconfigured"
    assert "denylist" in out.tail


async def test_run_verify_timeout_is_misconfigured(tmp_path: Path):
    out = await run_verify("sleep 5", tmp_path, timeout_s=0.2)
    assert out.status == "misconfigured"
    assert "timed out" in out.tail
