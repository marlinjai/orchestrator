import pytest


@pytest.fixture(autouse=True)
def _isolate_notify_env(monkeypatch):
    """Keep tests from ever reaching the real notification side channels.

    `notify()` fires in `run_orchestrator`'s `finally`, so without this guard a
    test run on a machine that has SECRETS_PROXY_TOKEN / ORCHESTRATOR_NOTIFY_URL
    in its env (e.g. launched via cc.sh) would POST to the live secrets-proxy or
    webhook and send real Telegram messages. Tests that exercise those channels
    set the vars explicitly inside the test, which overrides this fixture.
    """
    monkeypatch.delenv("SECRETS_PROXY_TOKEN", raising=False)
    monkeypatch.delenv("ORCHESTRATOR_NOTIFY_URL", raising=False)
