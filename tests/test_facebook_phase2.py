"""Additional Phase 2 live API tests, all using mocked Meta endpoints."""
from pathlib import Path
from unittest.mock import patch

import core.publish_manager as publish_manager
import integrations.facebook_publisher as facebook_publisher
from tests.test_facebook_publisher import VALID_PROBE
from integrations.facebook_publisher import FacebookApiError, FacebookPublisher, FacebookPublisherError, FacebookPublisherError


def _live_publisher(tmp_path):
    publisher = FacebookPublisher(dry_run=False)
    publisher.publish_enabled = True
    publisher.timeout_seconds = 10
    publisher.page_id = "page-123"
    publisher.access_token = "secret_token_value"
    history = tmp_path / "data" / "facebook_publish_history.json"
    return publisher, publish_manager.FacebookPublishManager(history_path=history)


def test_phase2_live_publish_succeeds(tmp_path, monkeypatch):
    publisher, manager = _live_publisher(tmp_path)
    video = Path(tmp_path / "world_general_knowledge_quiz_part_001.mp4")
    video.write_bytes(b"reel")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", lambda path: VALID_PROBE)
    monkeypatch.setattr(publisher, "_start_upload", lambda title, description: ("video-id", "upload-url"))
    monkeypatch.setattr(publisher, "_upload_binary", lambda upload_url, path: {"success": True})
    monkeypatch.setattr(publisher, "_finish_publish", lambda video_id, title, description: {"success": True, "post_id": "post-9"})
    calls = []
    monkeypatch.setattr(publisher, "_prior_published_record", lambda publish_manager, content_hash, part_number: None)

    result = publisher.publish_reel(1, video, "Title", "Description", manager)

    assert result["success"]
    assert result["meta_video_id"] == "video-id"
    assert result["meta_post_id"] == "post-9"
    assert calls == []
    record = manager.find_record(part_number=1, content_hash=result["content_hash"])
    assert record["status"] == "published"
    assert record["meta_post_id"] == "post-9"


def test_phase2_duplicate_record_skips_live_calls(tmp_path, monkeypatch):
    publisher, manager = _live_publisher(tmp_path)
    video = Path(tmp_path / "world_general_knowledge_quiz_part_001.mp4")
    video.write_bytes(b"reel")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", lambda path: VALID_PROBE)
    manager.upsert_record(
        {
            "part_number": 1,
            "content_hash": publisher.calculate_content_hash(video),
            "status": "published",
            "meta_video_id": "old-video",
            "meta_post_id": "old-post",
        }
    )
    start_calls = []
    monkeypatch.setattr(publisher, "_start_upload", lambda *args, **kwargs: start_calls.append(True))

    result = publisher.publish_reel(1, video, "Title", "Description", manager)
    assert result["skipped"] is True
    assert result["reason"] == "already_published"
    assert start_calls == []


def test_phase2_live_publish_is_disabled_by_default(tmp_path, monkeypatch):
    publisher = FacebookPublisher(dry_run=False)
    publisher.page_id = "page-123"
    publisher.access_token = "secret"
    video = Path(tmp_path / "world_general_knowledge_quiz_part_001.mp4")
    video.write_bytes(b"reel")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", lambda path: VALID_PROBE)

    raised = False
    try:
        publisher.publish_reel(1, video, "Title", "Description", publish_manager=None)
    except Exception as exc:
        raised = True
        assert "disabled" in str(exc).lower()
    assert raised


def test_phase2_failed_finish_is_recorded_without_false_success(tmp_path, monkeypatch):
    publisher, manager = _live_publisher(tmp_path)
    video = Path(tmp_path / "world_general_knowledge_quiz_part_001.mp4")
    video.write_bytes(b"reel")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", lambda path: VALID_PROBE)
    monkeypatch.setattr(publisher, "_start_upload", lambda title, description: ("video-id", "upload-url"))
    monkeypatch.setattr(publisher, "_upload_binary", lambda upload_url, path: {"success": True})
    monkeypatch.setattr(publisher, "_finish_publish", lambda video_id, title, description: (_ for _ in ()).throw(FacebookApiError("Meta rejected the reel")))
    monkeypatch.setattr(publisher, "_prior_published_record", lambda publish_manager, content_hash, part_number: None)

    raised = False
    try:
        publisher.publish_reel(1, video, "Title", "Description", manager)
    except FacebookApiError as exc:
        raised = True
        assert "rejected" in str(exc).lower()
    assert raised
    record = manager.find_record(part_number=1, content_hash=publisher.calculate_content_hash(video))
    assert record["status"] == "failed"
    assert record["meta_post_id"] is None


def test_phase2_api_errors_are_redacted(tmp_path, monkeypatch):
    publisher, _ = _live_publisher(tmp_path)
    result = publisher._redacted_error_body(b"{\"error\":{\"message\":\"Forbidden secret_token_value\"}}", 403)
    raised = True
    assert "secret_token_value" not in result
    assert raised

