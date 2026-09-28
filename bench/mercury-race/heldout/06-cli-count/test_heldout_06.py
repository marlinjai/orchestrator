import subprocess
import sys


def _run(*args):
    return subprocess.run([sys.executable, "-m", "textkit", *args], capture_output=True, text=True)


def test_counts(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("one two\nthree\n", encoding="utf-8")
    r = _run("count", str(f))
    assert r.returncode == 0
    assert r.stdout.strip() == "2 3 14"


def test_unicode_and_no_trailing_newline(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("héllo wörld", encoding="utf-8")
    r = _run("count", str(f))
    assert r.returncode == 0
    assert r.stdout.strip() == "1 2 11"


def test_missing_file(tmp_path):
    r = _run("count", str(tmp_path / "nope.txt"))
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.strip() != ""


def test_bad_usage():
    assert _run("frobnicate", "x").returncode == 2
    assert _run("count").returncode == 2
