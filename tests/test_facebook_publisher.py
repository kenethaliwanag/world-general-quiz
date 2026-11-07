"""Tests for the Phase 1 Facebook Reels publisher."""
import json
from pathlib import Path

import core.publish_manager as publish_manager
import integrations.facebook_publisher as facebook_publisher
from integrations.facebook_publisher import FacebookPublisher


def _stub_preflight(probe_json):
    def fake_run_ffprobe(video_path):
        return probe_json
    return fake_run_ffprobe


VALID_PROBE = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "r_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000", "bit_rate": "128000"},
    ],
    "format": {"duration": "2.5"},
}


def _video(tmp_path):
    path = tmp_path / "world_general_knowledge_quiz_part_001.mp4"
    path.write_bytes(b"reel")
    return path


def test_valid_preflight_passes(tmp_path, monkeypatch):
    publisher = FacebookPublisher(dry_run=True)
    video = _video(tmp_path)
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))
    result = publisher.validate_video(video)
    assert result.success
    assert not result.errors


def test_missing_video_fails_preflight(tmp_path, monkeypatch):
    publisher = FacebookPublisher(dry_run=True)
    result = publisher.validate_video(tmp_path / "missing.mp4")
    assert not result.success
    assert "does not exist" in result.errors[0]


def _invalid(tmp_path, monkeypatch, key, new_value):
    probe = json.loads(json.dumps(VALID_PROBE))
    stream = probe["streams"][1] if key.startswith(("audio", "channels", "sample", "bit")) else probe["streams"][0]
    if key == "resolution":
        probe["streams"][0]["width"] = 1280
        probe["streams"][0]["height"] = 720
    elif key == "frame_rate":
        probe["streams"][0]["r_frame_rate"] = "24/1"
    elif key == "video_codec":
        probe["streams"][0]["codec_name"] = "hevc"
    elif key == "audio_codec":
        probe["streams"][1]["codec_name"] = "mp3"
    elif key == "channels":
        probe["streams"][1]["channels"] = 1
    elif key == "sample_rate":
        probe["streams"][1]["sample_rate"] = "44100"
    elif key == "bitrate":
        probe["streams"][1]["bit_rate"] = "96000"
    else:
        raise ValueError(key)
    publisher = FacebookPublisher(dry_run=True)
    video = _video(tmp_path)
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", _stub_preflight(probe))
    result = publisher.validate_video(video)
    assert not result.success
    assert result.errors


def test_failed_preflight_cases(tmp_path, monkeypatch):
    for case in ("resolution", "frame_rate", "video_codec", "audio_codec", "channels", "sample_rate", "bitrate"):
        _invalid(tmp_path, monkeypatch, case, None)


def test_content_hash_consistency(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(facebook_publisher, "PROJECT_ROOT", tmp_path) if hasattr(facebook_publisher, "PROJECT_ROOT") else None
    video = _video(tmp_path)
    publisher = FacebookPublisher(dry_run=True)
    first = publisher.calculate_content_hash(video)
    second = publisher.calculate_content_hash(video)
    assert first == second
    video.write_bytes(b"changed")
    assert publisher.calculate_content_hash(video) != first


def test_dry_run_does_not_contact_meta(tmp_path, monkeypatch, capsys):
    history = tmp_path / "data" / "facebook_publish_history.json"
    manager = publish_manager.FacebookPublishManager(history_path=history)
    publisher = FacebookPublisher(dry_run=True)
    video = _video(tmp_path)
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))

    report = publisher.run_dry_run(
        1,
        video,
        "World General Knowledge Quiz - Part 1",
        "Answer in the comments.",
        publish_manager=manager,
    )
    captured = capsys.readouterr()
    assert report.success
    assert report.publication_status == "dry_run"
    payload = report.dry_run_payload
    assert "[redacted]" in str(payload["access_token"])
    assert "meta.graph.facebook.com" not in str(payload)
    assert "access_token" not in captured.out.lower()
    assert Path(report.report_path).exists()
    history = json.loads(history.read_text(encoding="utf-8"))
    assert history["records"][0]["status"] == "dry_run"


def test_dry_run_payload_contains_title_and_hash(tmp_path, monkeypatch):
    history = tmp_path / "data" / "facebook_publish_history.json"
    manager = publish_manager.FacebookPublishManager(history_path=history)
    publisher = FacebookPublisher(dry_run=True)
    video = _video(tmp_path)
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))

    report = publisher.run_dry_run(1, video, "Quiz Title", "Quiz Description", publish_manager=manager)
    payload = report.dry_run_payload
    assert payload["title"] == "Quiz Title"
    assert payload["description"] == "Quiz Description"
    assert payload["metadata"]["content_hash"] == report.content_hash
    assert payload["upload_phase"] == "start"


def test_dry_run_does_not_change_question_history(tmp_path, monkeypatch):
    history = tmp_path / "data" / "facebook_publish_history.json"
    question_history = tmp_path / "used_questions.json"
    question_history.write_text('{"used_ids":["q1"],"last_part":1}', encoding="utf-8")
    manager = publish_manager.FacebookPublishManager(history_path=history)
    publisher = FacebookPublisher(dry_run=True)
    video = _video(tmp_path)
    monkeypatch.setattr(facebook_publisher, "_run_ffprobe", _stub_preflight(VALID_PROBE))

    publisher.run_dry_run(1, video, "Title", "Description", publish_manager=manager)

    assert question_history.read_text(encoding="utf-8") == '{"used_ids":["q1"],"last_part":1}'


def test_malformed_publish_history_is_not_reset(tmp_path, monkeypatch):
    history = tmp_path / "data" / "facebook_publish_history.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(publish_manager, "PROJECT_ROOT", tmp_path)
    raised = False
    try:
        publish_manager.load_publish_history(history)
    except publish_manager.PublishHistoryError:
        raised = True
    assert raised
    assert history.read_text(encoding="utf-8") == "{bad json"
