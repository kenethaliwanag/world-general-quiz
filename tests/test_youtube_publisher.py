"""Tests for the independent YouTube Shorts publisher (dry-run by default)."""
import json
from pathlib import Path
from types import SimpleNamespace

import core.youtube_publish_manager as youtube_manager
import integrations.youtube_publisher as youtube_publisher
from core.youtube_publish_manager import YouTubePublishManager
from integrations.youtube_publisher import (
    YouTubeApiError,
    YouTubeConfigurationError,
    YouTubePublisher,
    YouTubePublisherError,
    YouTubeSessionExpiredError,
)


VALID_PROBE = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "r_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000", "bit_rate": "128000"},
    ],
    "format": {"duration": "60.0"},
}


def _stub_preflight(probe):
    def fake_run_ffprobe(video_path):
        return probe

    return fake_run_ffprobe


def _video(tmp_path, size=5):
    path = tmp_path / "world_general_knowledge_quiz_part_012_reel.mp4"
    path.write_bytes(b"r" * size)
    return path


def _stub_http(responses, calls):
    queue = list(responses)

    def fake_http(method, url, *, data=None, headers=None, timeout=30):
        calls.append({"method": method, "url": url, "data": data, "headers": headers or {}})
        return queue.pop(0)

    return fake_http


def _publisher(**kwargs):
    defaults = dict(
        client_id="CLIENT",
        client_secret="SECRET",
        refresh_token="REFRESH",
        dry_run=False,
        publish_enabled=True,
    )
    defaults.update(kwargs)
    return YouTubePublisher(**defaults)


def _token_response(scope=youtube_publisher.YOUTUBE_UPLOAD_SCOPE):
    payload = {"access_token": "ACCESS123", "expires_in": 3600}
    if scope is not None:
        payload["scope"] = scope
    return 200, {}, json.dumps(payload).encode("utf-8")


def _session_response(url="https://upload.example/session/SESSIONVALUE"):
    return 200, {"Location": url}, b""


def _enable_network(monkeypatch):
    monkeypatch.setattr(youtube_publisher, "NETWORK_UPLOADS_ENABLED", True)


# --- Credentials -----------------------------------------------------------

def test_credentials_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "ENV_CLIENT")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "ENV_SECRET")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "ENV_REFRESH")
    publisher = YouTubePublisher()
    assert publisher.client_id == "ENV_CLIENT"
    assert publisher.client_secret == "ENV_SECRET"
    assert publisher.refresh_token == "ENV_REFRESH"


def test_missing_credentials_reported():
    publisher = YouTubePublisher(client_id="", client_secret="", refresh_token="")
    errors = publisher.validate_configuration()
    assert any("YOUTUBE_CLIENT_ID" in error for error in errors)
    assert any("YOUTUBE_CLIENT_SECRET" in error for error in errors)
    assert any("YOUTUBE_REFRESH_TOKEN" in error for error in errors)


def test_incomplete_credentials_reported():
    publisher = YouTubePublisher(client_id="CLIENT", client_secret="", refresh_token="")
    errors = publisher.validate_configuration()
    assert not any("YOUTUBE_CLIENT_ID" in error for error in errors)
    assert len(errors) == 2


# --- Token exchange --------------------------------------------------------

def test_refresh_token_exchange(monkeypatch):
    _enable_network(monkeypatch)
    calls = []
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http([_token_response()], calls))
    result = _publisher().refresh_access_token()
    assert result["access_token"] == "ACCESS123"
    body = calls[0]["data"].decode("utf-8")
    assert "grant_type=refresh_token" in body
    assert "CLIENT" in body and "SECRET" in body and "REFRESH" in body
    assert "client_secret" in body


def test_failed_token_exchange(monkeypatch):
    _enable_network(monkeypatch)
    body = b'{"error": {"message": "invalid refresh token"}}'
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http([(400, {}, body)], []))
    try:
        _publisher().refresh_access_token()
    except YouTubeApiError as exc:
        assert exc.status_code == 400
        assert "invalid refresh token" in str(exc)
    else:
        raise AssertionError("Expected YouTubeApiError")


def test_upload_scope_validated_when_reported(monkeypatch):
    _enable_network(monkeypatch)
    monkeypatch.setattr(
        youtube_publisher,
        "_http_request",
        _stub_http([_token_response(scope="https://www.googleapis.com/auth/youtube.readonly")], []),
    )
    try:
        _publisher().refresh_access_token()
    except YouTubeConfigurationError as exc:
        assert "youtube.upload" in str(exc)
    else:
        raise AssertionError("Expected YouTubeConfigurationError")


def test_token_response_without_scope_still_accepted(monkeypatch):
    _enable_network(monkeypatch)
    monkeypatch.setattr(youtube_publisher, "_http_request", _stub_http([_token_response(scope=None)], []))
    assert _publisher().refresh_access_token()["access_token"] == "ACCESS123"


# --- Metadata --------------------------------------------------------------

def test_metadata_validation(tmp_path):
    publisher = _publisher()
    metadata = publisher.build_metadata(3, "a" * 64)
    assert not publisher.validate_metadata(metadata)
    bad = json.loads(json.dumps(metadata))
    bad["snippet"]["title"] = ""
    bad["snippet"]["description"] = "x" * 5001
    bad["snippet"]["tags"] = [1]
    bad["snippet"]["categoryId"] = "abc"
    errors = publisher.validate_metadata(bad)
    assert len(errors) >= 4


def test_privacy_status_validation():
    assert not _publisher(privacy_status="private").validate_configuration()
    assert not _publisher(privacy_status="unlisted").validate_configuration()
    assert _publisher(privacy_status="public").validate_configuration()
    try:
        _publisher(privacy_status="public").build_metadata(1, "hash")
    except YouTubeConfigurationError:
        pass
    else:
        raise AssertionError("Public uploads must be unavailable in this phase")


def test_metadata_contains_hash_marker():
    metadata = _publisher().build_metadata(7, "deadbeef")
    assert "Content hash: deadbeef" in metadata["snippet"]["description"]
    assert "#Shorts" in metadata["snippet"]["description"]


# --- Preflight -------------------------------------------------------------

def test_valid_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    result = _publisher().validate_video(_video(tmp_path))
    assert result.success, result.errors
    assert result.details["duration_seconds"] == 60.0


def test_missing_video_fails_preflight(tmp_path):
    result = _publisher().validate_video(tmp_path / "missing.mp4")
    assert not result.success
    assert "does not exist" in result.errors[0]


def test_preflight_rejects_bad_videos(tmp_path, monkeypatch):
    cases = {}
    resolution = json.loads(json.dumps(VALID_PROBE))
    resolution["streams"][0]["width"] = 1280
    cases["resolution"] = resolution
    fps = json.loads(json.dumps(VALID_PROBE))
    fps["streams"][0]["r_frame_rate"] = "24/1"
    cases["frame_rate"] = fps
    video_codec = json.loads(json.dumps(VALID_PROBE))
    video_codec["streams"][0]["codec_name"] = "hevc"
    cases["video_codec"] = video_codec
    audio_codec = json.loads(json.dumps(VALID_PROBE))
    audio_codec["streams"][1]["codec_name"] = "mp3"
    cases["audio_codec"] = audio_codec
    duration = json.loads(json.dumps(VALID_PROBE))
    duration["format"]["duration"] = "181.0"
    cases["duration"] = duration
    for name, probe in cases.items():
        monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(probe))
        result = _publisher().validate_video(_video(tmp_path))
        assert not result.success, name
        assert result.errors, name


def test_preflight_rejects_missing_audio(tmp_path, monkeypatch):
    probe = json.loads(json.dumps(VALID_PROBE))
    probe["streams"] = [probe["streams"][0]]
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(probe))
    assert not _publisher().validate_video(_video(tmp_path)).success


# --- Upload flow (mocked HTTP) ---------------------------------------------

def test_successful_upload_and_no_credentials_on_disk(tmp_path, monkeypatch):
    _enable_network(monkeypatch)
    calls = []
    monkeypatch.setattr(
        youtube_publisher,
        "_http_request",
        _stub_http(
            [_token_response(), _session_response(), (201, {}, json.dumps({"id": "VIDEO_ID_1"}).encode())],
            calls,
        ),
    )
    video = _video(tmp_path)
    result = _publisher(chunk_bytes=youtube_publisher.MIN_CHUNK_BYTES).publish(video, 12)
    assert result == {"youtube_video_id": "VIDEO_ID_1", "upload_status": "uploaded"}
    assert calls[0]["method"] == "POST" and "oauth2" in calls[0]["url"]
    assert "uploadType=resumable" in calls[1]["url"]
    assert calls[2]["method"] == "PUT"
    for path in tmp_path.rglob("*"):
        if path.is_file():
            text = path.read_bytes().decode("utf-8", errors="replace")
            assert "SESSIONVALUE" not in text
            assert "ACCESS123" not in text
            assert "REFRESH" not in text


def test_http_400_403_quota_errors(monkeypatch, tmp_path):
    _enable_network(monkeypatch)
    for status, message in ((400, "bad request"), (403, "quotaExceeded"), (403, "forbidden")):
        body = json.dumps({"error": {"message": message}}).encode("utf-8")
        calls = []
        monkeypatch.setattr(
            youtube_publisher,
            "_http_request",
            _stub_http([_token_response(), _session_response(), (status, {"X-Goog-Reason": "rateLimitExceeded"}, body)], calls),
        )
        try:
            _publisher().publish(_video(tmp_path), 1)
        except YouTubeApiError as exc:
            assert exc.status_code == status
        else:
            raise AssertionError(f"Expected YouTubeApiError for {status}")


def test_resumable_308_resume(monkeypatch, tmp_path):
    _enable_network(monkeypatch)
    chunk = youtube_publisher.MIN_CHUNK_BYTES
    video = _video(tmp_path, chunk + 10)
    calls = []
    monkeypatch.setattr(
        youtube_publisher,
        "_http_request",
        _stub_http(
            [
                _token_response(),
                _session_response(),
                (308, {"Range": f"bytes=0-{chunk - 1}"}, b""),
                (201, {}, json.dumps({"id": "VIDEO_ID_2"}).encode()),
            ],
            calls,
        ),
    )
    result = _publisher(chunk_bytes=chunk).publish(video, 12)
    assert result["youtube_video_id"] == "VIDEO_ID_2"
    puts = [call for call in calls if call["method"] == "PUT"]
    assert len(puts) == 2
    assert puts[0]["headers"]["Content-Range"] == f"bytes 0-{chunk - 1}/{chunk + 10}"
    assert puts[1]["headers"]["Content-Range"] == f"bytes {chunk}-{chunk + 9}/{chunk + 10}"


def test_expired_upload_session(monkeypatch, tmp_path):
    _enable_network(monkeypatch)
    calls = []
    monkeypatch.setattr(
        youtube_publisher,
        "_http_request",
        _stub_http([_token_response(), _session_response(), (404, {}, b'{"error":{"message":"gone"}}')], calls),
    )
    try:
        _publisher().publish(_video(tmp_path), 12)
    except YouTubeSessionExpiredError:
        pass
    else:
        raise AssertionError("Expected YouTubeSessionExpiredError")


def test_no_progress_resume_is_rejected(monkeypatch, tmp_path):
    _enable_network(monkeypatch)
    calls = []
    monkeypatch.setattr(
        youtube_publisher,
        "_http_request",
        _stub_http([_token_response(), _session_response(), (308, {}, b"")], calls),
    )
    try:
        _publisher().publish(_video(tmp_path), 12)
    except YouTubePublisherError as exc:
        assert "no progress" in str(exc)
    else:
        raise AssertionError("Expected a no-progress error")


def test_error_redaction(monkeypatch, tmp_path):
    _enable_network(monkeypatch)
    body = json.dumps(
        {"error": {"message": "denied SECRET and https://upload.example/session/SESSIONVALUE"}}
    ).encode("utf-8")
    calls = []
    monkeypatch.setattr(
        youtube_publisher,
        "_http_request",
        _stub_http([_session_response(), (403, {}, body)], calls),
    )
    publisher = _publisher()
    session_url = publisher._start_resumable_session("ACCESS123", publisher.build_metadata(1, "hash"), 5)
    try:
        publisher.upload_resumable(session_url, _video(tmp_path), "ACCESS123")
    except YouTubeApiError as exc:
        message = str(exc)
        assert "SECRET" not in message
        assert "SESSIONVALUE" not in message
        assert "[REDACTED]" in message
    else:
        raise AssertionError("Expected YouTubeApiError")


def test_network_disabled_by_default(tmp_path):
    publisher = _publisher()
    for call in (publisher.refresh_access_token, lambda: publisher.publish(_video(tmp_path), 1)):
        try:
            call()
        except YouTubePublisherError as exc:
            assert "disabled" in str(exc)
        else:
            raise AssertionError("Network uploads must be disabled in Phase 2.7.1")


# --- Dry-run ---------------------------------------------------------------

def test_dry_run_performs_zero_http_requests_and_no_history_write(tmp_path, monkeypatch):
    history = tmp_path / "data" / "youtube_publish_history.json"
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    monkeypatch.setattr(youtube_publisher, "_http_request", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("HTTP called")))
    publisher = YouTubePublisher()
    report = publisher.run_dry_run(12, _video(tmp_path), YouTubePublishManager(history_path=history))
    assert report.success
    assert report.publication_status == "dry_run"
    assert report.would_upload is True
    assert not history.exists()


def test_dry_run_detects_existing_upload(tmp_path, monkeypatch):
    history = tmp_path / "data" / "youtube_publish_history.json"
    manager = YouTubePublishManager(history_path=history)
    video = _video(tmp_path)
    content_hash = youtube_publisher.YouTubePublisher().calculate_content_hash(video)
    manager.record(
        {
            "part_number": 12,
            "video_file_name": video.name,
            "content_hash": content_hash,
            "youtube_video_id": "OLDVIDEO",
            "upload_status": "uploaded",
            "privacy_status": "private",
            "created_at": "2026-01-01T00:00:00+00:00",
            "published_at": "2026-01-01T00:00:00+00:00",
            "errors": [],
        }
    )
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    report = YouTubePublisher().run_dry_run(12, video, manager)
    assert report.existing_record["youtube_video_id"] == "OLDVIDEO"
    assert report.would_upload is False


def test_cli_dry_run_uses_existing_reel(tmp_path, monkeypatch, capsys):
    import main

    reel_dir = tmp_path / "output" / "part_012" / "facebook" / "reels"
    reel_dir.mkdir(parents=True)
    (reel_dir / "world_general_knowledge_quiz_part_012_reel.mp4").write_bytes(b"reel")
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(youtube_manager, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    monkeypatch.setattr(youtube_publisher, "_http_request", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("HTTP called")))

    main._run_publish_youtube(
        SimpleNamespace(part=12, youtube_privacy="unlisted", youtube_dry_run=True)
    )
    output = capsys.readouterr().out
    assert "world_general_knowledge_quiz_part_012_reel.mp4" in output
    assert "unlisted" in output
    assert "No OAuth request" in output


def test_cli_fails_closed_when_live_flags_requested(monkeypatch):
    import main

    monkeypatch.setattr("config.YOUTUBE_PUBLISH_ENABLED", True)
    monkeypatch.setattr("config.YOUTUBE_PUBLISH_DRY_RUN", False)
    try:
        main._run_publish_youtube(SimpleNamespace(part=1, youtube_privacy=None, youtube_dry_run=False))
    except SystemExit as exc:
        assert "not available in Phase 2.7.1" in str(exc)
    else:
        raise AssertionError("CLI must fail closed for live flags")
