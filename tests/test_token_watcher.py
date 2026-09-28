"""M9 token watcher: the handover threshold follows the Worker model's window,
and the handover trigger and saturation guard read the measured context size."""

import pytest

from orchestrator.executor import ExecutorProfile, handover_threshold, load_executor_config
from orchestrator.state import IterationUsage, context_size

CLAUDE = ExecutorProfile(role="worker", model_id="claude-opus-4-8")
MERCURY = ExecutorProfile(role="worker", model_id="mercury-2", provider="inception")


def test_threshold_is_capped_at_seventy_percent_of_the_window():
    assert handover_threshold(MERCURY, 200_000) == 89_600  # 0.7 x 128K
    assert handover_threshold(CLAUDE, 200_000) == 140_000
    assert handover_threshold(CLAUDE, 80_000) == 80_000  # the operator value when lower
    assert handover_threshold(MERCURY, 0) == 0  # disabled stays disabled


def test_window_override_from_config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[executors.worker]\nmodel_id = "mercury-2"\nprovider = "inception"\n'
        "context_window_tokens = 32000\n"
    )
    prof = load_executor_config(p)["worker"]
    assert prof.context_window == 32_000
    assert handover_threshold(prof, 80_000) == 22_400


@pytest.mark.parametrize("value", ['"12"', "10", "true"])
def test_bad_window_is_rejected(tmp_path, value):
    p = tmp_path / "config.toml"
    p.write_text(f"[executors.worker]\ncontext_window_tokens = {value}\n")
    with pytest.raises(ValueError, match="context_window_tokens"):
        load_executor_config(p)


def test_context_size_prefers_the_measured_peak():
    assert context_size(IterationUsage(iteration=1, input_tokens=500_000, context_tokens=40_000)) == 40_000
    assert context_size(IterationUsage(iteration=1, input_tokens=5_000)) == 5_000
