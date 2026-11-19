"""Tests for the manual, private-only YouTube Shorts upload workflow."""
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.youtube_publish_manager as youtube_manager
import integrations.youtube_publisher as youtube_publisher
import main as app
from core.youtube_publish_manager import YouTubePublishManager
from integrations.youtube_publisher import (
    NETWORK_UPLOAD_ENV_FLAG,
    YouTubeConfigurationError,
    YouTubePublisher,
    YouTubePublisherError,
)


WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "youtube-test-upload.yml"

VALID_PROBE = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "r_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000", "bit_rate": "128000"},
    ],
    "format": {"duration": "60.0"},
}


def _stub_preflight(probe):
    return lambda video_path: probe


@pytest.fixture(autouse=True)
def stub_ffprobe(monkeypatch):
    """Unit tests never call real ffprobe; individual tests may override with a bad probe."""
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))


def _stub_http(responses, calls=None):
    queue = list(responses)
    calls = calls if calls is not None else []

    def fake_http(method, url, *, data=None, headers=None, timeout=30):
        calls.append({"method": method, "url": url, "data": data, "headers": headers or {}})
        return queue.pop(0)

    return fake_http


def _video(tmp_path):
    path = tmp_path / "world_general_knowledge_quiz_part_012_reel.mp4"
    path.write_bytes(b"r" * 100)
    return path


def _publisher(channel_id="CHANNEL_OK", **kwargs):
    defaults = dict(
        client_id="CLIENT",
        client_secret="SECRET",
        refresh_token="REFRESH",
        channel_id=channel_id,
        privacy_status="private",
        dry_run=False,
        publish_enabled=True,
    )
    defaults.update(kwargs)
    return YouTubePublisher(**defaults)


def _unlock(monkeypatch, enabled=True):
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", enabled)
    monkeypatch.setenv(NETWORK_UPLOAD_ENV_FLAG, "true" if enabled else "")


def _success_responses(channel_id="CHANNEL_OK"):
    token = (200, {}, json.dumps({"access_token": "ACCESS123", "expires_in": 3600}).encode())
    session = (200, {"Location": "https://upload.example/session/SESSIONVALUE"}, b"")
    uploaded = (201, {}, json.dumps({"id": "VIDEO_OK", "snippet": {"channelId": channel_id}}).encode())
    return [token, session, uploaded]


def _record(part=12, content_hash="a" * 64, status="uploaded", video_id="OLDVIDEO", **extra):
    record = {
        "part_number": part,
        "video_file_name": "world_general_knowledge_quiz_part_012_reel.mp4",
        "content_hash": content_hash,
        "content_type": "youtube_shorts",
        "title": "World General Knowledge Quiz | Part 012 #Shorts",
        "youtube_video_id": video_id,
        "upload_status": status,
        "privacy_status": "private",
        "created_at": "2026-01-01T00:00:00+00:00",
        "published_at": "2026-01-01T00:00:00+00:00",
        "errors": [],
    }
    record.update(extra)
    return record


def _setup_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(youtube_manager, "PROJECT_ROOT", tmp_path)
    for name in youtube_publisher.SECRET_ENV_NAMES:
        monkeypatch.setenv(name, f"env-{name}")
    monkeypatch.setenv(NETWORK_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr("config.YOUTUBE_PUBLISH_ENABLED", True)
    monkeypatch.setattr("config.YOUTUBE_PUBLISH_DRY_RUN", False)
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))


# --- Workflow configuration ------------------------------------------------

def test_workflow_is_manual_only_and_private():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    trigger_section = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger_section
    assert "schedule:" not in trigger_section
    assert "pull_request:" not in trigger_section
    assert "  push:" not in trigger_section
    assert "concurrency:" in text
    assert 'group: youtube-shorts-publish' in text
    assert 'YOUTUBE_ALLOW_NETWORK_UPLOAD: "true"' in text
    assert 'YOUTUBE_PRIVACY_STATUS: "private"' in text
    assert "--youtube-upload --part" in text
    assert "META_" not in text
    assert "--publish-content-type" not in text


def _workflow_step(name):
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    start = text.index(f"- name: {name}")
    end = text.find("\n      - name:", start + 1)
    return text[start:] if end == -1 else text[start:end]


def test_generation_step_only_generates_the_reel():
    step = _workflow_step("Generate exactly one Reel")
    assert "--render-reels" in step and "--reels-question-count 5" in step
    for forbidden in ("git add", "git commit", "git push"):
        assert forbidden not in step
    assert "persisted by the final always-run step" in step


def test_persistence_step_covers_both_histories_and_runs_always():
    step = _workflow_step("Persist question and YouTube publication history")
    assert "if: always()" in step
    assert "git status --porcelain -- data/used_questions.json data/youtube_publish_history.json" in step
    assert 'git add -- "${PATHS[@]}"' in step
    for path in ("data/used_questions.json", "data/youtube_publish_history.json"):
        assert path in step
    assert "git add ." not in step and "git add -A" not in step
    assert "steps.upload.outcome" not in step and "success()" not in step
    assert "data/facebook_publish_history.json" not in step


def test_question_history_survives_later_upload_failure():
    generation = _workflow_step("Generate exactly one Reel")
    persistence = _workflow_step("Persist question and YouTube publication history")
    artifact = _workflow_step("Upload generated outputs and YouTube history as artifacts")
    assert "git commit" not in generation
    assert "if: always()" in persistence
    assert "data/used_questions.json" in persistence
    assert "needs:" not in persistence
    assert "data/used_questions.json" in artifact


def test_unchanged_histories_cause_no_commit():
    step = _workflow_step("Persist question and YouTube publication history")
    assert 'CHANGED="$(git status --porcelain -- data/used_questions.json data/youtube_publish_history.json)"' in step
    assert 'if [ -z "$CHANGED" ]; then' in step
    assert "git diff --quiet -- data/youtube_publish_history.json" not in step


def test_persistence_stages_only_allowed_paths_and_fails_on_conflict():
    step = _workflow_step("Persist question and YouTube publication history")
    assert "Refusing to commit unexpected staged file" in step
    assert "if ! git rebase origin/main; then" in step
    assert "if ! git push origin HEAD:main; then" in step
    assert "--force" not in step
    assert "git push origin HEAD:main" in step


def test_workflow_checks_secrets_presence_only():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "--youtube-check-secrets" in text
    for name in youtube_publisher.SECRET_ENV_NAMES:
        assert f"{name}: ${{{{ secrets.{name} }}}}" in text


# --- Secret checks ---------------------------------------------------------

def test_secret_presence_helper_reports_missing(monkeypatch):
    import pytest

    for name in youtube_publisher.SECRET_ENV_NAMES:
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "SECRETVALUE_A")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "SECRETVALUE_B")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "SECRETVALUE_C")
    assert youtube_publisher.check_secret_presence() == ["YOUTUBE_CHANNEL_ID"]
    with pytest.raises(SystemExit) as exc:
        app._run_youtube_secret_check()
    assert "YOUTUBE_CHANNEL_ID" in str(exc.value)


def test_secret_check_never_prints_values(monkeypatch, capsys):
    for name in youtube_publisher.SECRET_ENV_NAMES:
        monkeypatch.setenv(name, "SECRETVALUE_XYZ")
    app._run_youtube_secret_check()
    output = capsys.readouterr().out
    assert "SECRETVALUE_XYZ" not in output
    assert output.count("PRESENT") == 4


def test_cli_missing_secret_fails(tmp_path, monkeypatch):
    _setup_cli(tmp_path, monkeypatch)
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "")
    try:
        app._run_youtube_upload(SimpleNamespace(part=12))
    except SystemExit as exc:
        assert "YOUTUBE_CHANNEL_ID" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for missing secret")


# --- Privacy and unlock gate ----------------------------------------------

def test_private_only_upload_rejects_other_privacy(monkeypatch, tmp_path):
    _unlock(monkeypatch)
    video = _video(tmp_path)
    manager = YouTubePublishManager(history_path=tmp_path / "history.json")
    for privacy in ("public", "unlisted"):
        publisher = _publisher(privacy_status=privacy)
        try:
            publisher.publish_once(12, video, manager)
        except YouTubePublisherError as exc:
            assert "private" in str(exc).lower()
        else:
            raise AssertionError(f"{privacy} must be rejected")


def test_upload_locked_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", False)
    monkeypatch.delenv(NETWORK_UPLOAD_ENV_FLAG, raising=False)
    video = _video(tmp_path)
    manager = YouTubePublishManager(history_path=tmp_path / "history.json")
    try:
        _publisher().publish_once(12, video, manager)
    except YouTubePublisherError as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("Upload must be locked by default")


def test_env_flag_unlocks_controlled_path(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", False)
    monkeypatch.setenv(NETWORK_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http(_success_responses()))
    result = _publisher().publish_once(
        12, _video(tmp_path), YouTubePublishManager(history_path=tmp_path / "history.json")
    )
    assert result["success"] is True


# --- Channel verification --------------------------------------------------

def test_channel_match_records_uploaded(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    calls = []
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http(_success_responses(), calls))
    history = tmp_path / "data" / "youtube_publish_history.json"
    result = _publisher().publish_once(12, _video(tmp_path), YouTubePublishManager(history_path=history))
    assert result["success"] is True
    assert result["youtube_video_id"] == "VIDEO_OK"
    assert result["channel_id"] == "CHANNEL_OK"
    assert calls and calls[-1]["method"] == "PUT"
    record = json.loads(history.read_text(encoding="utf-8"))["records"][0]
    assert record["upload_status"] == "uploaded"
    assert record["privacy_status"] == "private"
    assert "SESSIONVALUE" not in history.read_text(encoding="utf-8")


def test_channel_mismatch_is_failure_with_video_id(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    monkeypatch.setattr(
        youtube_publisher,
        "_http_request",
        _stub_http(_success_responses(channel_id="WRONG_CHANNEL")),
    )
    history = tmp_path / "data" / "youtube_publish_history.json"
    result = _publisher().publish_once(12, _video(tmp_path), YouTubePublishManager(history_path=history))
    assert result["success"] is False
    assert result["needs_reconciliation"] is True
    assert result["youtube_video_id"] == "VIDEO_OK"
    record = json.loads(history.read_text(encoding="utf-8"))["records"][0]
    assert record["upload_status"] == "failed"
    assert record["youtube_video_id"] == "VIDEO_OK"
    assert "Manual reconciliation" in record["errors"][0]


def test_missing_channel_id_stops_before_network(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    calls = []
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http([], calls))
    try:
        _publisher(channel_id="").publish_once(
            12, _video(tmp_path), YouTubePublishManager(history_path=tmp_path / "h.json")
        )
    except YouTubeConfigurationError as exc:
        assert "YOUTUBE_CHANNEL_ID" in str(exc)
    else:
        raise AssertionError("Expected YouTubeConfigurationError")
    assert not calls


# --- Video validation and duplicates --------------------------------------

def test_missing_reel_cli_fails(tmp_path, monkeypatch):
    _setup_cli(tmp_path, monkeypatch)
    try:
        app._run_youtube_upload(SimpleNamespace(part=999))
    except SystemExit as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for missing Reel")


def test_invalid_preflight_stops_before_upload(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    bad_probe = json.loads(json.dumps(VALID_PROBE))
    bad_probe["streams"][0]["width"] = 1280
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(bad_probe))
    calls = []
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http([], calls))
    history = tmp_path / "data" / "youtube_publish_history.json"
    try:
        _publisher().publish_once(12, _video(tmp_path), YouTubePublishManager(history_path=history))
    except YouTubePublisherError as exc:
        assert "preflight" in str(exc).lower()
    else:
        raise AssertionError("Expected preflight failure")
    assert not calls
    assert not history.exists()


def test_duplicate_upload_is_skipped_without_http(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    video = _video(tmp_path)
    manager = YouTubePublishManager(history_path=tmp_path / "h.json")
    content_hash = youtube_publisher.YouTubePublisher().calculate_content_hash(video)
    manager.record(_record(content_hash=content_hash))
    monkeypatch.setattr(
        youtube_publisher, "_http_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP called"))
    )
    result = _publisher().publish_once(12, video, manager)
    assert result["skipped"] is True
    assert result["success"] is True


def test_existing_history_preserved(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http(_success_responses()))
    history = tmp_path / "data" / "youtube_publish_history.json"
    manager = YouTubePublishManager(history_path=history)
    manager.record(_record(part=7, content_hash="b" * 64))
    result = _publisher().publish_once(12, _video(tmp_path), manager)
    assert result["success"] is True
    records = json.loads(history.read_text(encoding="utf-8"))["records"]
    assert len(records) == 2
    assert records[0]["part_number"] == 7
    assert records[1]["part_number"] == 12


# --- Failure handling ------------------------------------------------------

def test_failed_upload_is_recorded_as_failed(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    responses = _success_responses()[:2]
    responses.append((403, {"X-Goog-Reason": "quotaExceeded"}, b'{"error":{"message":"quota denied SECRET"}}'))
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http(responses))
    history = tmp_path / "data" / "youtube_publish_history.json"
    result = _publisher().publish_once(12, _video(tmp_path), YouTubePublishManager(history_path=history))
    assert result["success"] is False
    assert result["needs_reconciliation"] is False
    record = json.loads(history.read_text(encoding="utf-8"))["records"][0]
    assert record["upload_status"] == "failed"
    assert "SECRET" not in str(record)


def test_uncertain_upload_is_preserved_and_not_retried(tmp_path, monkeypatch):
    _unlock(monkeypatch)
    responses = _success_responses()[:2]
    responses.append((404, {}, b'{"error":{"message":"session gone"}}'))
    calls = []
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http(responses, calls))
    history = tmp_path / "data" / "youtube_publish_history.json"
    manager = YouTubePublishManager(history_path=history)
    result = _publisher().publish_once(12, _video(tmp_path), manager)
    assert result["needs_reconciliation"] is True
    assert result["status"] == "uploading"
    assert len([call for call in calls if call["method"] == "PUT"]) == 1
    second = _publisher().publish_once(12, _video(tmp_path), manager)
    assert second["skipped"] is True
    assert second["needs_reconciliation"] is True
    assert len([call for call in calls if call["method"] == "PUT"]) == 1


# --- Isolation and logging -------------------------------------------------

def test_cli_upload_does_not_call_facebook(tmp_path, monkeypatch, capsys):
    _setup_cli(tmp_path, monkeypatch)
    reel_dir = tmp_path / "output" / "part_012" / "facebook" / "reels"
    reel_dir.mkdir(parents=True)
    (reel_dir / "world_general_knowledge_quiz_part_012_reel.mp4").write_bytes(b"reel")
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", True)
    monkeypatch.setattr(
        youtube_publisher.YouTubePublisher,
        "publish_once",
        lambda self, part, video, manager: {
            "success": True, "skipped": False, "needs_reconciliation": False,
            "part_number": part, "status": "uploaded", "youtube_video_id": "VIDEO_OK",
        },
    )
    source = inspect.getsource(app._run_publish_youtube) + inspect.getsource(app._run_youtube_upload)
    assert "FacebookPublisher" not in source
    assert "publish-content-type" not in source
    assert "META_" not in source
    app._run_youtube_upload(SimpleNamespace(part=12))
    output = capsys.readouterr().out
    assert "VIDEO_OK" in output
    for secret in ("env-YOUTUBE_CLIENT_ID", "env-YOUTUBE_CLIENT_SECRET", "env-YOUTUBE_REFRESH_TOKEN"):
        assert secret not in output


def test_phase271_dry_run_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(youtube_manager, "PROJECT_ROOT", tmp_path)
    reel_dir = tmp_path / "output" / "part_012" / "facebook" / "reels"
    reel_dir.mkdir(parents=True)
    (reel_dir / "world_general_knowledge_quiz_part_012_reel.mp4").write_bytes(b"reel")
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    monkeypatch.setattr(
        youtube_publisher, "_http_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP called"))
    )
    app._run_publish_youtube(SimpleNamespace(part=12, youtube_privacy=None, youtube_dry_run=True))
    assert not (tmp_path / "data" / "youtube_publish_history.json").exists()
