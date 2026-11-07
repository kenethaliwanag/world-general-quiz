"""Tests for Facebook publication history management."""
import json
from pathlib import Path

import core.publish_manager as publish_manager


def test_load_missing_history_returns_empty_default(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    loaded = publish_manager.load_publish_history(path)
    assert loaded == {"schema_version": 1, "records": []}


def test_load_malformed_history_raises(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    path.write_text("{bad json", encoding="utf-8")
    try:
        publish_manager.load_publish_history(path)
        raised = False
    except publish_manager.PublishHistoryError:
        raised = True
    assert raised


def test_save_and_reload_preserves_records(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    history = {"schema_version": 1, "records": [{"part_number": 1, "status": "dry_run"}]}
    publish_manager.save_publish_history(history, path)
    loaded = publish_manager.load_publish_history(path)
    assert loaded["records"][0]["part_number"] == 1
    assert not any(path.parent.glob(".facebook_publish_history_*.tmp"))


def test_upsert_replaces_matching_record(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    manager = publish_manager.FacebookPublishManager(history_path=path)
    manager.upsert_record({"part_number": 1, "content_hash": "abc", "status": "dry_run"})
    manager.upsert_record({"part_number": 1, "content_hash": "abc", "status": "failed", "error_message": "network"})
    history = publish_manager.load_publish_history(path)
    assert len(history["records"]) == 1
    assert history["records"][0]["status"] == "failed"


def test_sha256_file_consistency(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    video = tmp_path / "part.mp4"
    video.write_bytes(b"exact quiz reel bytes")
    first = publish_manager.sha256_file(video)
    second = publish_manager.sha256_file(video)
    assert first == second
    assert len(first) == 64


def test_find_record_returns_matching_entry(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    manager = publish_manager.FacebookPublishManager(history_path=path)
    manager.upsert_record({"part_number": 2, "content_hash": "hash-value", "status": "dry_run"})
    found = manager.find_record(part_number=2, content_hash="hash-value")
    assert found is not None
    assert found["status"] == "dry_run"
