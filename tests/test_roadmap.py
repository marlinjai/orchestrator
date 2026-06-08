"""Tests for orchestrator.roadmap (roadmap-to-goal scaffolding)."""

import json

import pytest

from orchestrator import roadmap as rm


SAMPLE_ITEM = {
    "path": "/Users/x/software-dev/knowledge-base/plans/2026-06-08-closed-loop-sync-and-roadmap.md",
    "status": "decided",
    "leverage_label": "HIGH",
    "date": "2026-06-08",
    "title": "Closed-Loop Sync and Roadmap",
}


def test_slug_strips_date_prefix_and_kebabs():
    assert rm._slug(SAMPLE_ITEM) == "closed-loop-sync-and-roadmap"
    assert rm._slug({"title": "Some Plan!"}) == "some-plan"
    assert rm._slug({}) == "roadmap-item"


def test_item_to_goal_references_plan_and_leaves_project_for_operator():
    task_id, goal = rm.item_to_goal(SAMPLE_ITEM)
    assert task_id == "closed-loop-sync-and-roadmap"
    assert f"task: {task_id}" in goal
    assert SAMPLE_ITEM["path"] in goal
    assert "TODO(operator): set --project" in goal   # repo not auto-guessed
    assert "Definition of done" in goal


def test_write_goal_creates_file(tmp_path):
    task_id, goal = rm.item_to_goal(SAMPLE_ITEM)
    out = rm.write_goal(goal, task_id, tmp_path)
    assert out.exists() and out.name == f"{task_id}.md"
    assert out.read_text(encoding="utf-8") == goal


def test_next_goal_picks_index_and_writes(tmp_path, monkeypatch):
    items = [SAMPLE_ITEM, {"path": "/p/b.md", "status": "draft", "title": "Beta"}]
    monkeypatch.setattr(rm, "fetch_ranked_items", lambda *a, **k: items)
    res = rm.next_goal(["/roots"], tmp_path, index=1)
    assert res["task_id"] == "b"
    assert res["total"] == 2
    assert (tmp_path / "b.md").exists()


def test_next_goal_empty_queue_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "fetch_ranked_items", lambda *a, **k: [])
    with pytest.raises(rm.RoadmapError):
        rm.next_goal(["/roots"], tmp_path)


def test_next_goal_index_out_of_range_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "fetch_ranked_items", lambda *a, **k: [SAMPLE_ITEM])
    with pytest.raises(rm.RoadmapError):
        rm.next_goal(["/roots"], tmp_path, index=5)


def test_fetch_ranked_items_parses_cli_json(monkeypatch):
    class FakeProc:
        stdout = json.dumps([SAMPLE_ITEM])
        stderr = ""

    def fake_run(cmd, capture_output, text, check):
        assert "roadmap" in cmd and "items" in cmd
        assert "--root" in cmd
        return FakeProc()

    monkeypatch.setattr(rm.subprocess, "run", fake_run)
    items = rm.fetch_ranked_items(["/some/root"])
    assert items[0]["title"] == "Closed-Loop Sync and Roadmap"


def test_fetch_ranked_items_missing_cli_raises(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(rm.subprocess, "run", boom)
    with pytest.raises(rm.RoadmapError):
        rm.fetch_ranked_items(["/root"])
