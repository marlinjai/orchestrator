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


# --- Telegram via secrets-proxy ---------------------------------------------


def test_telegram_skipped_without_proxy_token(monkeypatch):
    """No SECRETS_PROXY_TOKEN: the telegram channel is a no-op (no proxy call)."""
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    called = {"n": 0}
    monkeypatch.setattr(
        notify_mod.urllib.request,
        "urlopen",
        lambda *a, **k: called.update(n=called["n"] + 1),
    )
    notify(task_id="t", status="completed")
    assert called["n"] == 0


def test_telegram_posts_to_proxy(monkeypatch):
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "proxy-tok")
    monkeypatch.setenv("SECRETS_PROXY_URL", "http://proxy.example:8765")
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["req"] = req

        class _R:
            def close(self):
                pass

        return _R()

    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", fake_urlopen)
    notify(task_id="lumitra-u1", status="escalated", reason="needs sign-off")
    req = captured["req"]
    assert req.full_url == "http://proxy.example:8765/execute"
    assert req.get_header("X-proxy-token") == "proxy-tok"
    body = json.loads(req.data.decode())
    assert body["path"] == "/monitoring"
    assert body["env"] == "production"
    assert body["projectId"]  # non-empty default
    assert "sendMessage" in body["command"]
    assert "$TELEGRAM_BOT_TOKEN" in body["command"]
    assert "$TELEGRAM_CHAT_ID" in body["command"]
    assert "lumitra-u1" in body["command"]


def test_telegram_shell_safety(monkeypatch):
    """A reason with shell metacharacters is shlex-quoted into the text arg, not
    executable; the static token refs stay intact."""
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "tok")
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["data"] = req.data.decode()

        class _R:
            def close(self):
                pass

        return _R()

    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", fake_urlopen)
    notify(task_id="t", status="failed", reason="boom '; rm -rf / #$(whoami) & ok")
    cmd = json.loads(captured["data"])["command"]
    assert "$TELEGRAM_BOT_TOKEN" in cmd  # static ref preserved
    assert "--data-urlencode" in cmd
    # the dangerous text is present but contained inside the single-quoted arg
    assert "rm -rf" in cmd


def test_telegram_failure_swallowed(monkeypatch):
    monkeypatch.setattr(notify_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("SECRETS_PROXY_TOKEN", "tok")

    def boom(*a, **k):
        raise OSError("proxy down")

    monkeypatch.setattr(notify_mod.urllib.request, "urlopen", boom)
    notify(task_id="t", status="completed")  # must not raise
