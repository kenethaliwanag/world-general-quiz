"""Tests for the independent YouTube publication history."""
import json

import core.youtube_publish_manager as manager
from core.youtube_publish_manager import (
    YouTubePublishHistoryError,
    YouTubePublishManager,
    load_publish_history,
    save_publish_history,
    upsert_record,
)


def _record(part=1, content_hash="a" * 64, status="uploaded", **extra):
    record = {
        "part_number": part,
        "video_file_name": f"world_general_knowledge_quiz_part_{part:03d}_reel.mp4",
        "content_hash": content_hash,
        "content_type": "youtube_shorts",
        "title": f"World General Knowledge Quiz - Part {part} #shorts",
        "youtube_video_id": "VIDEO1",
        "upload_status": status,
        "privacy_status": "private",
        "created_at": "2026-01-01T00:00:00+00:00",
        "published_at": "2026-01-01T00:00:00+00:00",
        "errors": [],
    }
    record.update(extra)
    return record


def _history(tmp_path):
    return tmp_path / "data" / "youtube_publish_history.json"


# --- Empty history and schema ---------------------------------------------

def test_empty_history(tmp_path):
    history = load_publish_history(_history(tmp_path))
    assert history == {"schema_version": 1, "records": []}


def test_save_empty_history(tmp_path):
    path = _history(tmp_path)
    save_publish_history({"schema_version": 1, "records": []}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"schema_version": 1, "records": []}


def test_schema_validation(tmp_path):
    bad_histories = [
        [],
        {"records": "not a list"},
        {"records": ["not an object"]},
        {"records": [_record(upload_status="published")]},
        {"records": [_record(content_type="reel")]},
        {"schema_version": "x", "records": []},
    ]
    for bad in bad_histories:
        try:
            manager.normalize_history(bad)
        except YouTubePublishHistoryError:
            continue
        raise AssertionError(f"Expected schema error for {bad}")


def test_corrupted_json_is_not_reset(tmp_path):
    path = _history(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad json", encoding="utf-8")
    try:
        load_publish_history(path)
    except YouTubePublishHistoryError:
        pass
    else:
        raise AssertionError("Expected YouTubePublishHistoryError")
    assert path.read_text(encoding="utf-8") == "{bad json"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    path = _history(tmp_path)
    save_publish_history({"schema_version": 1, "records": []}, path)
    assert [p.name for p in path.parent.iterdir()] == [path.name]


# --- Records ---------------------------------------------------------------

def test_record_insertion(tmp_path):
    path = _history(tmp_path)
    upsert_record(path, _record())
    records = load_publish_history(path)["records"]
    assert len(records) == 1
    assert records[0]["content_type"] == "youtube_shorts"
    assert records[0]["youtube_video_id"] == "VIDEO1"


def test_existing_records_preserved(tmp_path):
    path = _history(tmp_path)
    upsert_record(path, _record(part=1))
    upsert_record(path, _record(part=2, content_hash="b" * 64))
    records = load_publish_history(path)["records"]
    assert [record["part_number"] for record in records] == [1, 2]


def test_duplicate_part_and_hash_is_merged(tmp_path):
    path = _history(tmp_path)
    upsert_record(path, _record(upload_status="uploading"))
    upsert_record(path, _record(upload_status="uploaded", youtube_video_id="VIDEO2"))
    records = load_publish_history(path)["records"]
    assert len(records) == 1
    assert records[0]["upload_status"] == "uploaded"
    assert records[0]["youtube_video_id"] == "VIDEO2"


def test_changed_content_hash_creates_new_record(tmp_path):
    path = _history(tmp_path)
    upsert_record(path, _record())
    upsert_record(path, _record(content_hash="c" * 64))
    assert len(load_publish_history(path)["records"]) == 2


def test_find_and_duplicate_statuses(tmp_path):
    path = _history(tmp_path)
    upsert_record(path, _record(part=1, status="failed"))
    upsert_record(path, _record(part=2, content_hash="d" * 64, status="uploading"))
    manager_instance = YouTubePublishManager(history_path=path)
    assert manager_instance.find(part_number=1, content_hash="a" * 64)["upload_status"] == "failed"
    assert manager_instance.find(part_number=1, upload_status="uploaded") is None
    assert manager_instance.is_duplicate(1, "a" * 64) is False
    assert manager_instance.is_duplicate(2, "d" * 64) is True


def test_credentials_and_session_urls_are_not_stored(tmp_path):
    path = _history(tmp_path)
    record = _record(
        access_token="ACCESS",
        refresh_token="REFRESH",
        youtube_session_url="https://upload.example/session/SECRET",
        authorization="Bearer ACCESS",
        errors=["[REDACTED] upload failed"],
    )
    upsert_record(path, record)
    saved = load_publish_history(path)["records"][0]
    for key in ("access_token", "refresh_token", "youtube_session_url", "authorization"):
        assert key not in saved
    assert saved["errors"] == ["[REDACTED] upload failed"]
    text = path.read_text(encoding="utf-8")
    for value in ("ACCESS", "REFRESH", "SECRET"):
        assert value not in text


def test_independent_from_facebook_history(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "PROJECT_ROOT", tmp_path)
    facebook_history = tmp_path / "data" / "facebook_publish_history.json"
    facebook_history.parent.mkdir(parents=True, exist_ok=True)
    facebook_history.write_text('{"schema_version": 1, "records": []}', encoding="utf-8")
    before = facebook_history.read_text(encoding="utf-8")

    YouTubePublishManager().record(_record())

    assert manager.default_history_path() == _history(tmp_path)
    assert _history(tmp_path).exists()
    assert facebook_history.read_text(encoding="utf-8") == before
