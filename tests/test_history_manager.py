"""Tests for question-history storage."""
import json
from pathlib import Path

import core.history_manager as history_manager


def _history_file(tmp_path, monkeypatch, name="used_questions.json"):
    path = tmp_path / name
    monkeypatch.setattr(history_manager, "HISTORY_FILE", path)
    return path


def test_load_missing_history_returns_default(tmp_path, monkeypatch):
    path = _history_file(tmp_path, monkeypatch)
    assert history_manager.load_history() == {"used_ids": [], "last_part": 0}
    assert not path.exists()


def test_load_malformed_history_returns_default(tmp_path, monkeypatch):
    path = _history_file(tmp_path, monkeypatch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad json", encoding="utf-8")
    assert history_manager.load_history() == {"used_ids": [], "last_part": 0}


def test_normalize_history_rejects_bad_shapes(tmp_path, monkeypatch):
    normalized = history_manager._normalize_history({"used_ids": 1, "last_part": "bad"})
    assert normalized == {"used_ids": [], "last_part": 0}


def test_save_and_reload_history(tmp_path, monkeypatch):
    path = _history_file(tmp_path, monkeypatch)
    history_manager.save_history({"used_ids": ["q2", "q1", "q1"], "last_part": 3})
    assert json.loads(path.read_text(encoding="utf-8")) == {"used_ids": ["q2", "q1"], "last_part": 3}
    assert history_manager.load_history() == {"used_ids": ["q2", "q1"], "last_part": 3}


def test_record_question_usage_advances_history(tmp_path, monkeypatch):
    path = _history_file(tmp_path, monkeypatch)
    history_manager.save_history({"used_ids": ["q1"], "last_part": 1})
    original = history_manager.load_history()
    updated = history_manager.record_question_usage(original, ["q3", "q1", "q4"], 2)
    # A reused ID moves to the end so the next Part recycles a different one.
    assert updated["used_ids"] == ["q3", "q4", "q1"]
    assert updated["last_part"] == 2
    assert history_manager.load_history() == updated
    assert path.stat().st_size > 0


def test_reset_history_clears_history(tmp_path, monkeypatch):
    path = _history_file(tmp_path, monkeypatch)
    history_manager.save_history({"used_ids": ["q1"], "last_part": 2})
    history_manager.reset_history()
    assert history_manager.load_history() == {"used_ids": [], "last_part": 0}
