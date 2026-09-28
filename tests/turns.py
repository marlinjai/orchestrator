"""Shared fakes for the Worker turn seam (``orchestrator._run_one_turn``)."""

from orchestrator.state import ExecutorRecord, IterationUsage


def worker_record(iteration: int) -> ExecutorRecord:
    return ExecutorRecord.build(
        role="worker",
        executor="claude",
        provider="anthropic",
        model_id="fake-model",
        elapsed_ms=0,
        iteration=iteration,
    )


def worker_turn(chunks: list[str], iteration: int, input_tokens: int = 0):
    """The (chunks, usage, record) 3-tuple ``_run_one_turn`` returns."""
    return (
        chunks,
        IterationUsage(iteration=iteration, input_tokens=input_tokens),
        worker_record(iteration),
    )
