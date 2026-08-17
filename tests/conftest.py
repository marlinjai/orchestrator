import pytest


@pytest.fixture(autouse=True)
def _isolate_notify_env(monkeypatch):
    """Keep tests from ever reaching the real notification side channels.

    `notify()` fires in `run_orchestrator`'s `finally`, so without this guard a
    test run on a machine that has SECRETS_PROXY_TOKEN / ORCHESTRATOR_NOTIFY_URL
    in its env (e.g. launched via cc.sh) would POST to the live secrets-proxy or
    webhook and send real Telegram messages. Tests that exercise those channels
    set the vars explicitly inside the test, which overrides this fixture.

    The token file needs the same treatment and is easier to miss: unsetting the
    env var is not enough now that the token's home is
    `~/.config/secrets-proxy/token`, because the resolver falls back to the
    developer's real file. That is how a real rotated token ended up in a pytest
    assertion diff on 2026-08-17. Point the override at a path that cannot
    exist so the resolver finds nothing unless a test says otherwise.
    """
    monkeypatch.delenv("SECRETS_PROXY_TOKEN", raising=False)
    monkeypatch.delenv("ORCHESTRATOR_NOTIFY_URL", raising=False)
    monkeypatch.setenv(
        "SECRETS_PROXY_TOKEN_FILE", "/nonexistent/orchestrator-tests/proxy-token"
    )
