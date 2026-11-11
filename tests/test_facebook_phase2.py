"""Additional Phase 2 live API tests, all using mocked Meta endpoints."""
from pathlib import Path
from unittest.mock import patch

import core.publish_manager as publish_manager
import integrations.facebook_publisher as facebook_publisher
from tests.test_facebook_publisher import VALID_PROBE, _stub_preflight
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



def test_facebook_test_reel_workflow_requires_explicit_confirmation():
    workflow = Path(".github/workflows/facebook-test-reel.yml").read_text(encoding="utf-8")
    assert "confirm_live_publish:" in workflow
    assert "default: false" in workflow
    assert 'FACEBOOK_PUBLISH_ENABLED: "true"' in workflow
    assert 'FACEBOOK_PUBLISH_DRY_RUN: "false"' in workflow
    assert "--publish-content-type reel" in workflow
    assert "--publish-content-type full_video" not in workflow
    assert "schedule:" not in workflow
    assert " || true" not in workflow
    assert "secrets.META_PAGE_ID" in workflow
    assert "--meta-page" not in workflow


def test_scheduled_workflow_publishes_ten_question_facebook_page_video():
    workflow = Path(".github/workflows/scheduled-world-quiz-videos.yml").read_text(encoding="utf-8")
    assert '- cron: "0 10 * * *"' in workflow
    assert '- cron: "0 14 * * *"' in workflow
    assert 'FACEBOOK_PUBLISH_ENABLED: "true"' in workflow
    assert 'FACEBOOK_PUBLISH_DRY_RUN: "false"' in workflow
    assert "python main.py --publish --part" in workflow
    assert "secrets.META_PAGE_ACCESS_TOKEN" in workflow
    assert "--render-ten-video" in workflow
    assert "--publish-content-type ten_question_video" in workflow
    assert " || true" not in workflow


def test_workflows_never_cache_the_question_history():
    # A cached history file silently overwrote the committed one and kept every
    # run regenerating the same Part.  Git stays the only source of truth.
    for name in ("scheduled-world-quiz-videos.yml", "generate-world-quiz-videos.yml", "facebook-test-reel.yml"):
        workflow = Path(f".github/workflows/{name}").read_text(encoding="utf-8")
        assert "world-quiz-question-history" not in workflow
        assert "git add data/used_questions.json" in workflow


def test_phase2_ten_question_page_video_publish_succeeds(tmp_path, monkeypatch):
    publisher, manager = _live_publisher(tmp_path)
    video = Path(tmp_path, "world_general_knowledge_quiz_part_001_10_questions.mp4")
    video.write_bytes(b"ten-question video")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", lambda path: VALID_PROBE)
    monkeypatch.setattr(publisher, "_upload_page_video", lambda path, title, description: {"id": "ten-video-id", "post_id": "ten-post-id"})

    result = publisher.publish_ten_question_video(1, video, "10 Questions", "Trivia challenge", manager)

    assert result["success"]
    assert result["meta_video_id"] == "ten-video-id"
    assert result["meta_post_id"] == "ten-post-id"
    record = manager.find_record(part_number=1, content_hash=result["content_hash"])
    assert record["status"] == "published"
    assert record["content_type"] == "ten_question_video"


def test_phase2_ten_question_page_video_failure_is_recorded(tmp_path, monkeypatch):
    publisher, manager = _live_publisher(tmp_path)
    video = Path(tmp_path, "world_general_knowledge_quiz_part_001_10_questions.mp4")
    video.write_bytes(b"ten-question video")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", lambda path: VALID_PROBE)

    def failing_upload(path, title, description):
        raise FacebookApiError("Meta rejected the Page Video")

    monkeypatch.setattr(publisher, "_upload_page_video", failing_upload)

    raised = False
    try:
        publisher.publish_ten_question_video(1, video, "10 Questions", "Trivia challenge", manager)
    except FacebookApiError as exc:
        raised = True
        assert "rejected" in str(exc).lower()
    assert raised
    record = manager.find_record(part_number=1, content_hash=publisher.calculate_content_hash(video))
    assert record["status"] == "failed"
    assert record["content_type"] == "ten_question_video"


def test_ten_question_video_live_publish_uses_page_video_upload(tmp_path, monkeypatch):
    publisher, manager = _live_publisher(tmp_path)
    video = Path(tmp_path, "world_general_knowledge_quiz_part_001_10_questions.mp4")
    video.write_bytes(b"ten-question-video")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    monkeypatch.setattr(publisher, "_upload_page_video", lambda path, title, description: {"id": "page-video-10", "post_id": "post-10"})
    result = publisher.publish_ten_question_video(1, video, "Title", "Description", manager)
    assert result["success"] is True
    assert result["meta_video_id"] == "page-video-10"
    record = manager.find_record(part_number=1, content_hash=publisher.calculate_content_hash(video))
    assert record["content_type"] == "ten_question_video"
    assert record["status"] == "published"


def test_ten_question_video_dry_run_uses_page_video_endpoint(tmp_path, monkeypatch):
    publisher = FacebookPublisher(dry_run=True)
    manager = publish_manager.FacebookPublishManager(history_path=tmp_path / "data" / "facebook_publish_history.json")
    video = Path(tmp_path, "world_general_knowledge_quiz_part_001_10_questions.mp4")
    video.write_bytes(b"ten-question-video")
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    report = publisher.run_dry_run(1, video, "Title", "Description", manager, content_type="ten_question_video")
    assert report.dry_run_payload["endpoint"].endswith("/videos")
