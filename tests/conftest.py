import pytest


@pytest.fixture(autouse=True)
def _isolate_machine_env(monkeypatch):
    """Keep tests from ever reaching the real notification side channels or the
    developer's operator config.

    `notify()` fires in `run_orchestrator`'s `finally`, so without this guard a
    test run on a machine that has ORCHESTRATOR_NOTIFY_URL in its env (e.g.
    launched via cc.sh) would POST to the live webhook and send real
    notifications. Tests that exercise those channels set the vars explicitly
    inside the test, which overrides this fixture.

    The secrets-proxy-call CLI needs the same treatment and is easier to miss:
    a machine that has actually built the CLI at its default path
    (`~/software-dev/secrets-proxy/mcp/dist/cli.js`) would otherwise have
    every unguarded test spawn a real `node` process that mints a real
    Infisical access token and reaches the live proxy. Point the override at a
    path that cannot exist so the resolver finds nothing unless a test says
    otherwise (this mirrors the shared-proxy-token version of this guard that
    protected a real rotated token from ending up in a pytest assertion diff
    on 2026-08-17; there is no token to leak any more, but a live network call
    from the test suite is still the failure mode to prevent).
    """
    monkeypatch.delenv("ORCHESTRATOR_NOTIFY_URL", raising=False)
    monkeypatch.setenv(
        "SECRETS_PROXY_CLI", "/nonexistent/orchestrator-tests/secrets-proxy-cli.js"
    )
    # The operator config (config.toml: [executors.*], the Marlin Proxy, the
    # repo registry) must never leak in from the developer's machine: a real
    # [executors.recon] entry would make every loop test fire a live recon call.
    # Tests that need a config point this at their own tmp dir.
    monkeypatch.setenv("ORCHESTRATOR_CONFIG_HOME", "/nonexistent/orchestrator-tests/config")
    monkeypatch.delenv("ORCHESTRATOR_EXECUTORS_FILE", raising=False)
