from orchestrator.held_out import decide_after_held_out
from orchestrator.verify import VerifyOutcome


def _outcome(status, exit_code=0, tail="") -> VerifyOutcome:
    return VerifyOutcome(status=status, exit_code=exit_code, tail=tail, command="cmd")


def test_held_out_pass_completes():
    d = decide_after_held_out(_outcome("pass"))
    assert d.action == "complete"
    assert d.exit_reason is None


def test_held_out_fail_after_intree_pass_is_fingerprint():
    d = decide_after_held_out(_outcome("fail", 1, "boom"), intree_verified=True)
    assert d.action == "escalate"
    assert "reward-hack fingerprint" in d.exit_reason.lower()
    assert "boom" in d.exit_reason


def test_held_out_fail_as_sole_gate_no_fingerprint_claim():
    d = decide_after_held_out(_outcome("fail", 1, "boom"), intree_verified=False)
    assert d.action == "escalate"
    assert "reward-hack" not in d.exit_reason.lower()
    assert "not trustworthy" in d.exit_reason.lower()


def test_held_out_misconfigured_escalates():
    d = decide_after_held_out(_outcome("misconfigured", None, "denylisted"))
    assert d.action == "escalate"
    assert "misconfigured" in d.exit_reason.lower()
