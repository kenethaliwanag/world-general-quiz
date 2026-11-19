"""Tests for scheduled public YouTube publishing and manual private isolation."""
import json
from pathlib import Path
from types import SimpleNamespace

import main
import integrations.youtube_publisher as youtube_publisher
from core.youtube_output import SHORTS_CONTENT_TYPE, TEN_QUESTION_CONTENT_TYPE, next_youtube_part_number, youtube_ten_question_video_path
from core.youtube_publish_manager import YouTubePublishManager
from integrations.youtube_publisher import YouTubePublisher


ROOT = Path(__file__).resolve().parents[1]
SCHEDULED = ROOT / ".github" / "workflows" / "scheduled-world-quiz-videos.yml"
MANUAL = ROOT / ".github" / "workflows" / "youtube-test-upload.yml"


def _publisher(privacy="private", **kwargs):
    defaults = dict(
        client_id="CLIENT", client_secret="SECRET", refresh_token="REFRESH",
        channel_id="CHANNEL_OK", privacy_status=privacy, dry_run=False,
        publish_enabled=True, content_type=TEN_QUESTION_CONTENT_TYPE,
    )
    defaults.update(kwargs)
    return YouTubePublisher(**defaults)


def _setup_video(tmp_path, monkeypatch):
    root = tmp_path / "output" / "youtube"
    video = youtube_ten_question_video_path(1, root)
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"video")
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    for name in youtube_publisher.SECRET_ENV_NAMES:
        monkeypatch.setenv(name, "present")
    monkeypatch.setenv(youtube_publisher.NETWORK_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr("config.YOUTUBE_PUBLISH_ENABLED", True)
    monkeypatch.setattr("config.YOUTUBE_PUBLISH_DRY_RUN", False)
    return root


# --- Workflow configuration ------------------------------------------------

def test_scheduled_workflow_runs_at_both_pht_times():
    text = SCHEDULED.read_text(encoding="utf-8")
    assert '- cron: "0 10 * * *" # 06:00 PM PHT' in text
    assert '- cron: "0 16 * * *" # 12:00 AM PHT' in text
    assert "schedule:" in text
    assert "group: world-quiz-generation" in text


def test_scheduled_workflow_generates_exactly_ten_youtube_questions():
    text = SCHEDULED.read_text(encoding="utf-8")
    assert "TEN_QUESTION_CONTENT_TYPE" in text
    assert "next_youtube_part_number" in text
    assert "youtube_ten_question_video_path" in text
    assert "--count 10" in text
    for flag in ("--render-ten-video", "--ten-question-count 10", "--youtube-ten-question-video",
                 "--output-root output/youtube"):
        assert flag in text, flag
    assert "len(questions) != 10" in text


def test_scheduled_workflow_public_upload_flags_and_command():
    text = SCHEDULED.read_text(encoding="utf-8")
    assert 'YOUTUBE_PRIVACY_STATUS: "public"' in text
    assert 'YOUTUBE_ALLOW_PUBLIC_UPLOAD: "true"' in text
    assert 'YOUTUBE_ALLOW_NETWORK_UPLOAD: "true"' in text
    assert "python main.py --youtube-video-upload" in text
    assert "--youtube-scheduled-upload" in text


def test_scheduled_workflow_persists_both_histories_safely():
    text = SCHEDULED.read_text(encoding="utf-8")
    step = text.split("- name: Persist YouTube publication history and question history", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "if: always() && github.event_name == 'schedule'" in step
    assert "git status --porcelain -- data/used_questions.json data/youtube_publish_history.json" in step
    assert "git fetch origin" in step and "git rebase origin/main" in step
    assert "--force" not in step
    assert "git push origin HEAD:main" in step
    assert "data/facebook_publish_history.json" not in step


def test_manual_workflow_remains_private_and_manual_only():
    text = MANUAL.read_text(encoding="utf-8")
    trigger = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger and "schedule:" not in trigger
    assert 'YOUTUBE_PRIVACY_STATUS: "private"' in text
    assert "YOUTUBE_ALLOW_PUBLIC_UPLOAD" not in text
    assert "--youtube-scheduled-upload" not in text
    assert "group: world-quiz-generation" in text


def test_facebook_scheduled_publishing_unchanged():
    text = SCHEDULED.read_text(encoding="utf-8")
    for marker in ('FACEBOOK_PUBLISH_ENABLED: "true"', 'FACEBOOK_PUBLISH_DRY_RUN: "false"',
                   "--publish-content-type ten_question_video", "secrets.META_PAGE_ACCESS_TOKEN",
                   "Record Facebook Page Video publication"):
        assert marker in text, marker


def test_retry_cannot_duplicate_upload_or_part(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    manager = YouTubePublishManager(history_path=history)
    record = {
        "part_number": 1, "video_file_name": "video.mp4", "content_hash": "c" * 64,
        "content_type": TEN_QUESTION_CONTENT_TYPE, "title": "Title",
        "youtube_video_id": "PUBLISHED", "upload_status": "uploaded",
        "privacy_status": "public", "created_at": "2026-01-01T00:00:00+00:00",
        "published_at": "2026-01-01T00:00:00+00:00", "errors": [],
    }
    manager.record(record)
    assert manager.is_duplicate(1, "c" * 64, TEN_QUESTION_CONTENT_TYPE)
    assert not manager.is_duplicate(1, "c" * 64, SHORTS_CONTENT_TYPE)
    assert next_youtube_part_number(history_path=history, content_type=TEN_QUESTION_CONTENT_TYPE) == 2
    assert json.loads(history.read_text(encoding="utf-8"))["records"][0]["youtube_video_id"] == "PUBLISHED"


# --- Publisher privacy gate ------------------------------------------------

def test_public_rejected_without_unlock(monkeypatch):
    monkeypatch.delenv(youtube_publisher.PUBLIC_UPLOAD_ENV_FLAG, raising=False)
    publisher = _publisher("public")
    assert publisher.validate_configuration()
    metadata = {
        "snippet": {"title": "Title", "description": "Description", "tags": ["quiz"], "categoryId": "27"},
        "status": {"privacyStatus": "public"},
    }
    assert publisher.validate_metadata(metadata)
    try:
        publisher.build_metadata(1, "hash")
    except youtube_publisher.YouTubeConfigurationError:
        pass
    else:
        raise AssertionError("build_metadata must reject public without the unlock")
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", True)
    try:
        publisher._require_network_allowed()
    except youtube_publisher.YouTubePublisherError as exc:
        assert "public" in str(exc).lower()
    else:
        raise AssertionError("Public upload must be rejected without the unlock")


def test_public_allowed_with_explicit_unlock(monkeypatch):
    monkeypatch.setenv(youtube_publisher.PUBLIC_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", True)
    publisher = _publisher("public")
    assert not publisher.validate_configuration()
    metadata = publisher.build_metadata(1, "hash")
    assert not publisher.validate_metadata(metadata)
    publisher._require_network_allowed()


def test_unlisted_still_rejected_for_network_upload(monkeypatch):
    monkeypatch.setenv(youtube_publisher.PUBLIC_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", True)
    try:
        _publisher("unlisted")._require_network_allowed()
    except youtube_publisher.YouTubePublisherError:
        pass
    else:
        raise AssertionError("Unlisted network upload must stay rejected")


# --- CLI scheduled vs manual privacy ---------------------------------------

def _capture_upload(monkeypatch):
    seen = {}

    def fake_publish_once(self, part, video, manager):
        seen["privacy"] = self.privacy_status
        seen["content_type"] = self.content_type
        return {
            "success": True, "skipped": False, "needs_reconciliation": False,
            "part_number": part, "status": "uploaded", "youtube_video_id": "VIDEO",
        }

    monkeypatch.setattr(YouTubePublisher, "publish_once", fake_publish_once)
    return seen


def test_scheduled_cli_uses_public_privacy(tmp_path, monkeypatch):
    root = _setup_video(tmp_path, monkeypatch)
    monkeypatch.setenv(youtube_publisher.PUBLIC_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr("config.YOUTUBE_PRIVACY_STATUS", "public")
    seen = _capture_upload(monkeypatch)
    main._run_youtube_video_upload(
        SimpleNamespace(part=1, output_root=str(root), youtube_scheduled_upload=True)
    )
    assert seen["privacy"] == "public"
    assert seen["content_type"] == TEN_QUESTION_CONTENT_TYPE


def test_manual_cli_stays_private_even_with_public_config(tmp_path, monkeypatch):
    root = _setup_video(tmp_path, monkeypatch)
    monkeypatch.setenv(youtube_publisher.PUBLIC_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr("config.YOUTUBE_PRIVACY_STATUS", "public")
    seen = _capture_upload(monkeypatch)
    main._run_youtube_video_upload(
        SimpleNamespace(part=1, output_root=str(root), youtube_scheduled_upload=False)
    )
    assert seen["privacy"] == "private"


def test_scheduled_cli_requires_public_unlock(tmp_path, monkeypatch):
    root = _setup_video(tmp_path, monkeypatch)
    monkeypatch.delenv(youtube_publisher.PUBLIC_UPLOAD_ENV_FLAG, raising=False)
    monkeypatch.setattr("config.YOUTUBE_PRIVACY_STATUS", "public")
    try:
        main._run_youtube_video_upload(
            SimpleNamespace(part=1, output_root=str(root), youtube_scheduled_upload=True)
        )
    except SystemExit as exc:
        assert "PUBLIC" in str(exc) or "public" in str(exc)
    else:
        raise AssertionError("Scheduled upload must fail without the public unlock")


def test_scheduled_cli_requires_public_privacy_setting(tmp_path, monkeypatch):
    root = _setup_video(tmp_path, monkeypatch)
    monkeypatch.setenv(youtube_publisher.PUBLIC_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr("config.YOUTUBE_PRIVACY_STATUS", "private")
    try:
        main._run_youtube_video_upload(
            SimpleNamespace(part=1, output_root=str(root), youtube_scheduled_upload=True)
        )
    except SystemExit as exc:
        assert "YOUTUBE_PRIVACY_STATUS=public" in str(exc)
    else:
        raise AssertionError("Scheduled upload must require public privacy configuration")
