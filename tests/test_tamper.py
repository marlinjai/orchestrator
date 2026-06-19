import subprocess
from pathlib import Path

import pytest

from orchestrator.tamper import count_assertions, is_test_path, scan_tamper


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "t@example.com"], repo)
    _run(["git", "config", "user.name", "T"], repo)
    _run(["git", "config", "commit.gpgsign", "false"], repo)
    return repo


def _commit_all(repo: Path, message: str) -> None:
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", message], repo)


def _head(repo: Path) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


# --- path + assertion heuristics ---

@pytest.mark.parametrize(
    "path",
    [
        "tests/test_foo.py",
        "src/__tests__/foo.test.ts",
        "app/foo.spec.tsx",
        "pkg/foo_test.go",
        "spec/models/user_spec.rb",
        "test_top_level.py",
    ],
)
def test_is_test_path_true(path):
    assert is_test_path(path)


@pytest.mark.parametrize(
    "path",
    ["src/foo.py", "app/index.ts", "README.md", "lib/contestant.py", "src/latest.ts"],
)
def test_is_test_path_false(path):
    assert not is_test_path(path)


def test_count_assertions_js_and_py():
    js = "describe('x', () => { it('a', () => { expect(1).toBe(1); expect(2).toEqual(2); }); });"
    # describe( it( expect( .toBe( expect( .toEqual(
    assert count_assertions(js) == 6
    py = "def test_x():\n    assert foo == 1\n    self.assertEqual(a, b)\n"
    assert count_assertions(py) == 2


# --- scan_tamper ---

def test_scan_no_baseline_is_noop(git_repo: Path):
    report = scan_tamper(git_repo, None, ["tests/test_a.py"])
    assert not report.tripped
    assert report.strong_paths == []


def test_scan_flags_deleted_test(git_repo: Path):
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
    _commit_all(git_repo, "seed tests")
    baseline = _head(git_repo)
    # Worker deletes the failing test and commits.
    (git_repo / "tests" / "test_a.py").unlink()
    _commit_all(git_repo, "remove test")

    report = scan_tamper(git_repo, baseline, ["tests/test_a.py"])
    assert report.tripped
    assert "tests/test_a.py" in report.strong_paths
    assert any("deleted" in d for d in report.details)


def test_scan_flags_dropped_assertions(git_repo: Path):
    (git_repo / "tests").mkdir()
    test = git_repo / "tests" / "test_a.py"
    test.write_text(
        "def test_a():\n    assert 1 == 1\n    assert 2 == 2\n    assert 3 == 3\n"
    )
    _commit_all(git_repo, "seed")
    baseline = _head(git_repo)
    # Worker guts two assertions to make a red test green.
    test.write_text("def test_a():\n    assert 1 == 1\n")
    _commit_all(git_repo, "weaken")

    report = scan_tamper(git_repo, baseline, ["tests/test_a.py"])
    assert report.tripped
    assert "tests/test_a.py" in report.strong_paths
    assert any("dropped" in d for d in report.details)


def test_scan_allows_added_assertions_log_only(git_repo: Path):
    (git_repo / "tests").mkdir()
    test = git_repo / "tests" / "test_a.py"
    test.write_text("def test_a():\n    assert 1 == 1\n")
    _commit_all(git_repo, "seed")
    baseline = _head(git_repo)
    # Strengthening tests is legit work: log signal, never a trip.
    test.write_text("def test_a():\n    assert 1 == 1\n    assert 2 == 2\n")
    _commit_all(git_repo, "strengthen")

    report = scan_tamper(git_repo, baseline, ["tests/test_a.py"])
    assert not report.tripped
    assert "tests/test_a.py" in report.log_paths


def test_scan_new_test_file_is_not_tamper(git_repo: Path):
    (git_repo / "seed.txt").write_text("x\n")
    _commit_all(git_repo, "seed")
    baseline = _head(git_repo)
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "test_new.py").write_text("def test_new():\n    assert 1\n")
    _commit_all(git_repo, "add test")

    report = scan_tamper(git_repo, baseline, ["tests/test_new.py"])
    assert not report.tripped
    assert report.log_paths == []


def test_scan_ignores_non_test_files(git_repo: Path):
    (git_repo / "src.py").write_text("x = 1\nassert x\nassert x\n")
    _commit_all(git_repo, "seed")
    baseline = _head(git_repo)
    (git_repo / "src.py").write_text("x = 1\n")  # dropped asserts, but not a test file
    _commit_all(git_repo, "edit src")

    report = scan_tamper(git_repo, baseline, ["src.py"])
    assert not report.tripped
    assert report.log_paths == []
