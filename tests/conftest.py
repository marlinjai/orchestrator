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


@pytest.fixture(autouse=True)
def _no_bash_sandbox_in_tests(monkeypatch):
    """Many tests start the real Claude CLI process through the SDK (without
    sending a model request). With the Bash sandbox required and a runner that
    lacks bubblewrap and socat (a bare Linux CI image), that process refuses to
    start (`failIfUnavailable`), which is exactly what it should do in
    production and exactly what a hermetic unit test must not depend on. So
    `build_worker_options` gets a disabled sandbox here. The real settings and
    the platform checks are unit-tested through the real `build_bash_sandbox`
    in test_worker.py, and the sandbox itself is proved against the real SDK by
    scripts/prove_confinement.py."""
    from orchestrator import worker

    monkeypatch.setattr(worker, "build_bash_sandbox", lambda *_a, **_k: {"enabled": False})
    # The same for the Mercury adapter's run_command: tests run plain bash so
    # they do not need sandbox-exec or bubblewrap. The real argv builder and the
    # refusal are unit-tested in test_worker.py / test_openai_compat_worker.py.
    from orchestrator.adapters import openai_compat_worker

    monkeypatch.setattr(
        openai_compat_worker, "sandboxed_command_argv", lambda command, work_dir: ["/bin/bash", "-c", command]
    )
