import json

import orchestrator.notify as notify_mod
from orchestrator.notify import TERMINAL_STATUSES, notify


def test_notify_never_raises_without_channels(monkeypatch):
    """No webhook + non-darwin: notify is a safe no-op, never raises."""
    monkeypatch.delenv("ORCHESTRATOR_NOTIFY_URL", raising=False)
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    notify(task_id="t", status="completed", reason="done")  # must not raise


def test_notify_macos_invoked_on_darwin(monkeypatch):
    calls = []
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(notify_mod.shutil, "which", lambda _: "/usr/bin/osascript")
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.delenv("ORCHESTRATOR_NOTIFY_URL", raising=False)
    notify(task_id="task-x", status="completed", reason="all good")
    assert len(calls) == 1
    argv = calls[0][0]
    assert "osascript" in argv[0]
    joined = " ".join(argv)
    assert "task-x" in joined and "all good" in joined


def test_notify_macos_skipped_off_darwin(monkeypatch):
    calls = []
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **k: calls.append(a))
    notify(task_id="t", status="failed")
    assert calls == []


def test_notify_webhook_posts_when_url_set(monkeypatch):
    posted = {}
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")

    def fake_urlopen(req, timeout=0):
        posted["url"] = req.full_url
        posted["data"] = req.data

        class _R:
            def close(self):
                pass

        return _R()

    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", fake_urlopen)
    notify(
        task_id="t1",
        status="failed",
        reason="boom",
        webhook_url="https://ntfy.example/topic",
    )
    assert posted["url"] == "https://ntfy.example/topic"
    assert b"failed" in posted["data"]
    assert b"boom" in posted["data"]


def test_notify_webhook_skipped_without_url(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    monkeypatch.delenv("ORCHESTRATOR_NOTIFY_URL", raising=False)
    monkeypatch.setattr(
        notify_mod.urllib.request,
        "urlopen",
        lambda *a, **k: called.update(n=called["n"] + 1),
    )
    notify(task_id="t", status="completed")
    assert called["n"] == 0


def test_notify_webhook_uses_env_when_no_arg(monkeypatch):
    posted = {}
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("ORCHESTRATOR_NOTIFY_URL", "https://ntfy.example/from-env")

    def fake_urlopen(req, timeout=0):
        posted["url"] = req.full_url

        class _R:
            def close(self):
                pass

        return _R()

    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", fake_urlopen)
    notify(task_id="t", status="completed")
    assert posted["url"] == "https://ntfy.example/from-env"


def test_notify_webhook_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", boom)
    # must not raise despite the webhook blowing up
    notify(task_id="t", status="completed", webhook_url="https://ntfy.example/x")


def test_notify_truncates_long_reason(monkeypatch):
    captured = []
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(notify_mod.shutil, "which", lambda _: "/usr/bin/osascript")
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **k: captured.append(a))
    notify(task_id="t", status="completed", reason="x" * 500)
    script = " ".join(captured[0][0])
    assert "..." in script  # truncated


def test_terminal_statuses_cover_state_machine():
    assert TERMINAL_STATUSES == {"completed", "escalated", "stopped", "failed"}


# --- Telegram via secrets-proxy (secrets-proxy-call CLI, no token here) -----


def test_telegram_skipped_without_cli(monkeypatch, tmp_path):
    """No secrets-proxy-call CLI built: the telegram channel is a no-op (no
    subprocess call)."""
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv(notify_mod.PROXY_CLI_ENV, str(tmp_path / "missing" / "cli.js"))
    called = {"n": 0}
    monkeypatch.setattr(
        notify_mod.subprocess, "run", lambda *a, **k: called.update(n=called["n"] + 1)
    )
    notify(task_id="t", status="completed")
    assert called["n"] == 0


def test_telegram_skipped_without_node(monkeypatch, tmp_path):
    """The CLI file exists but node is not on PATH: still a no-op."""
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv(notify_mod.PROXY_CLI_ENV, str(cli))
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: None)
    called = {"n": 0}
    monkeypatch.setattr(
        notify_mod.subprocess, "run", lambda *a, **k: called.update(n=called["n"] + 1)
    )
    notify(task_id="t", status="completed")
    assert called["n"] == 0


def _fake_run_result(returncode=0, stderr=""):
    class _R:
        pass

    r = _R()
    r.returncode = returncode
    r.stderr = stderr
    return r


def test_telegram_pipes_execute_body_into_the_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv(notify_mod.PROXY_CLI_ENV, str(cli))
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/node")
    captured = {}

    def fake_run(argv, *, input, capture_output, text, timeout, check):
        captured["argv"] = argv
        captured["input"] = input
        return _fake_run_result()

    monkeypatch.setattr(notify_mod.subprocess, "run", fake_run)
    notify(task_id="lumitra-u1", status="escalated", reason="needs sign-off")
    assert captured["argv"] == ["node", str(cli), "execute"]
    body = json.loads(captured["input"])
    assert body["path"] == "/monitoring"
    assert body["env"] == "production"
    assert body["projectId"]  # non-empty default
    assert "sendMessage" in body["command"]
    assert "$TELEGRAM_BOT_TOKEN" in body["command"]
    assert "$TELEGRAM_CHAT_ID" in body["command"]
    assert "lumitra-u1" in body["command"]
    # No token anywhere: no header, no bearer, no X-Proxy-Token.
    assert "X-Proxy-Token" not in captured["input"]
    assert "bearer" not in captured["input"].lower()


def test_telegram_shell_safety(monkeypatch, tmp_path):
    """A reason with shell metacharacters is shlex-quoted into the text arg, not
    executable; the static token refs stay intact."""
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv(notify_mod.PROXY_CLI_ENV, str(cli))
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/node")
    captured = {}

    def fake_run(argv, *, input, capture_output, text, timeout, check):
        captured["input"] = input
        return _fake_run_result()

    monkeypatch.setattr(notify_mod.subprocess, "run", fake_run)
    notify(task_id="t", status="failed", reason="boom '; rm -rf / #$(whoami) & ok")
    cmd = json.loads(captured["input"])["command"]
    assert "$TELEGRAM_BOT_TOKEN" in cmd  # static ref preserved
    assert "--data-urlencode" in cmd
    # the dangerous text is present but contained inside the single-quoted arg
    assert "rm -rf" in cmd


def test_telegram_failure_swallowed(monkeypatch, tmp_path):
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv(notify_mod.PROXY_CLI_ENV, str(cli))
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/node")

    def boom(*a, **k):
        raise OSError("cli spawn failed")

    monkeypatch.setattr(notify_mod.subprocess, "run", boom)
    notify(task_id="t", status="completed")  # must not raise


def test_telegram_nonzero_exit_swallowed(monkeypatch, tmp_path):
    """A non-2xx from the proxy (surfaced by the CLI's non-zero exit) is a
    swallowed best-effort failure too, not a raise out of notify()."""
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv(notify_mod.PROXY_CLI_ENV, str(cli))
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(
        notify_mod.subprocess,
        "run",
        lambda *a, **k: _fake_run_result(returncode=1, stderr="403 forbidden"),
    )
    notify(task_id="t", status="completed")  # must not raise
