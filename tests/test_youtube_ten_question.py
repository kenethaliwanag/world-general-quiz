"""Regression tests for YouTube's 10-question tracker video format."""
import json
from pathlib import Path
from types import SimpleNamespace

import core.history_manager as history_manager
import core.question_manager as question_manager
import core.script_exporter as exporter
import core.youtube_publish_manager as youtube_manager
import integrations.youtube_publisher as youtube_publisher
import main
from core.youtube_output import (
    SHORTS_CONTENT_TYPE,
    TEN_QUESTION_CONTENT_TYPE,
    next_youtube_part_number,
    youtube_ten_question_video_path,
)
from core.youtube_publish_manager import YouTubePublishManager
from integrations.youtube_publisher import YouTubePublisher


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "youtube-test-upload.yml"
VALID_PROBE = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "r_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000", "bit_rate": "128000"},
    ],
    "format": {"duration": "600.0"},
}


def _args(part=1, output_root=None, youtube_ten=False, render_ten=True, count=10):
    return SimpleNamespace(
        count=count, category="all", difficulty="all", seed=42, part=part,
        start_part=None, total_parts=None, tts=False, render=False,
        reset_history=False, render_reels=False, render_facebook_reels=False,
        facebook_reels=False, reels_question_count=5, facebook_reels_question_count=None,
        render_ten_video=render_ten, render_facebook_ten_video=False,
        facebook_ten_video=False, facebook_ten_question_count=10,
        output_root=output_root, youtube_shorts=False,
        youtube_ten_question_video=youtube_ten,
    )


def _bank(tmp_path, monkeypatch, used=5, last_part=27):
    questions = [
        {"id": f"q{i}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, 21)
    ]
    q_file = tmp_path / "questions.json"
    q_file.write_text(json.dumps(questions), encoding="utf-8")
    h_file = tmp_path / "data" / "used_questions.json"
    h_file.parent.mkdir(parents=True, exist_ok=True)
    h_file.write_text(
        json.dumps({"used_ids": [f"q{i}" for i in range(1, used + 1)], "last_part": last_part}),
        encoding="utf-8",
    )
    monkeypatch.setattr(history_manager, "HISTORY_FILE", h_file)
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", q_file)
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(exporter, "OUTPUT_DIR", tmp_path / "output")

    compositions = []

    def fake_create(quiz, audio_map=None, content_type="full", tracker=None, output_root=None, **kwargs):
        root = Path(output_root) if output_root else main.OUTPUT_DIR
        project = root / "hyperframes" / f"part_{quiz['part']:03d}"
        if content_type == "reel":
            project = project / "reels"
        elif content_type.startswith("ten_question"):
            project = project / "videos"
        project.mkdir(parents=True, exist_ok=True)
        (project / "index.html").write_text("composition", encoding="utf-8")
        compositions.append({"content_type": content_type, "tracker": tracker, "project": project})
        return project, 1.0, {}

    def fake_render(project_dir, part_number, output_path=None, **kwargs):
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake mp4")
        return target

    monkeypatch.setattr(main, "create_composition", fake_create)
    monkeypatch.setattr(main, "render_video", fake_render)
    return h_file, compositions


def _publisher(content_type=SHORTS_CONTENT_TYPE, **kwargs):
    defaults = dict(
        client_id="CLIENT", client_secret="SECRET", refresh_token="REFRESH",
        channel_id="CHANNEL_OK", privacy_status="private", dry_run=False,
        publish_enabled=True,
    )
    defaults.update(kwargs)
    return YouTubePublisher(content_type=content_type, **defaults)


def _record(part, content_type, video_id="VIDEO", content_hash="a" * 64, status="uploaded"):
    return {
        "part_number": part, "video_file_name": "video.mp4", "content_hash": content_hash,
        "content_type": content_type, "title": "Title", "youtube_video_id": video_id,
        "upload_status": status, "privacy_status": "private",
        "created_at": "2026-01-01T00:00:00+00:00", "published_at": "2026-01-01T00:00:00+00:00",
        "errors": [],
    }


# --- Output paths and generation ------------------------------------------

def test_youtube_ten_question_path_is_distinct():
    shorts = ROOT / "output" / "youtube" / "part_001" / "youtube" / "shorts" / "world_general_knowledge_quiz_part_001.mp4"
    ten = youtube_ten_question_video_path(1)
    assert ten.as_posix().endswith("output/youtube/part_001/youtube/videos/world_general_knowledge_quiz_part_001_10_questions.mp4")
    assert ten != shorts


def test_generation_selects_and_writes_exactly_ten_questions(tmp_path, monkeypatch):
    h_file, compositions = _bank(tmp_path, monkeypatch)
    root = tmp_path / "output" / "youtube"
    main.generate_part(1, _args(output_root=str(root), youtube_ten=True))

    video = youtube_ten_question_video_path(1, root)
    assert video.is_file()
    quiz = json.loads((video.parent / "script.json").read_text(encoding="utf-8"))
    assert len(quiz["questions"]) == 10
    assert (video.parent / "subtitles" / "part_001.srt").is_file()
    assert (video.parent / "narration").is_dir()
    assert any(c["content_type"] == "ten_question_video" and c["tracker"] is True for c in compositions)
    assert not any(p.name == "facebook" for p in (root / "part_001").rglob("*"))
    assert h_file.read_text(encoding="utf-8")  # global history still present


def test_facebook_ten_question_path_unchanged(tmp_path, monkeypatch):
    _bank(tmp_path, monkeypatch)
    main.generate_part(1, _args(youtube_ten=False))
    assert (tmp_path / "output" / "part_001" / "facebook" / "videos" / "world_general_knowledge_quiz_part_001_10_questions.mp4").is_file()
    assert not (tmp_path / "output" / "youtube").exists()


def test_question_history_and_facebook_numbering_untouched(tmp_path, monkeypatch):
    h_file, _ = _bank(tmp_path, monkeypatch)
    before = json.loads(h_file.read_text(encoding="utf-8"))
    assert history_manager.next_part_number() == 28
    main.generate_part(1, _args(output_root=str(tmp_path / "output" / "youtube"), youtube_ten=True))
    after = json.loads(h_file.read_text(encoding="utf-8"))
    assert set(after) == {"used_ids", "last_part"}
    assert after["last_part"] == 27
    assert history_manager.next_part_number() == 28
    assert set(before["used_ids"]).issubset(set(after["used_ids"]))


# --- Publisher validation and metadata ------------------------------------

def test_ten_question_format_has_no_shorts_duration_limit(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", lambda path: VALID_PROBE)
    assert _publisher(TEN_QUESTION_CONTENT_TYPE).validate_video(video).success
    result = _publisher(SHORTS_CONTENT_TYPE).validate_video(video)
    assert not result.success
    assert any("180s" in error for error in result.errors)


def test_ten_question_metadata_has_no_shorts_branding():
    publisher = _publisher(TEN_QUESTION_CONTENT_TYPE)
    metadata = publisher.build_metadata(1, "hash")
    snippet = metadata["snippet"]
    assert snippet["title"] == "World General Knowledge Quiz | Part 001 | 10 Questions"
    assert "score out of 10" in snippet["description"]
    assert "#Shorts" not in json.dumps(snippet)
    for tag in ("general knowledge", "quiz", "trivia", "education", "10 questions"):
        assert tag in snippet["tags"]


def test_shorts_metadata_backward_compatible():
    metadata = _publisher(SHORTS_CONTENT_TYPE).build_metadata(12, "hash")
    assert "#shorts" in metadata["snippet"]["title"]
    assert "#Shorts" in metadata["snippet"]["description"]
    assert "shorts" in metadata["snippet"]["tags"]


# --- History coexistence ---------------------------------------------------

def test_history_accepts_both_content_types(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    manager = YouTubePublishManager(history_path=history)
    manager.record(_record(1, SHORTS_CONTENT_TYPE, "yEgHXZc2Gls"))
    manager.record(_record(1, TEN_QUESTION_CONTENT_TYPE, "NEWVIDEO"))
    records = json.loads(history.read_text(encoding="utf-8"))["records"]
    assert len(records) == 2
    assert records[0]["youtube_video_id"] == "yEgHXZc2Gls"
    assert records[1]["content_type"] == TEN_QUESTION_CONTENT_TYPE


def test_duplicate_checks_distinguish_content_types(tmp_path):
    history = {
        "schema_version": 1,
        "records": [_record(1, SHORTS_CONTENT_TYPE, "yEgHXZc2Gls", content_hash="b" * 64)],
    }
    assert youtube_manager.is_duplicate(history, 1, "b" * 64, SHORTS_CONTENT_TYPE)
    assert not youtube_manager.is_duplicate(history, 1, "b" * 64, TEN_QUESTION_CONTENT_TYPE)
    path = tmp_path / "youtube_publish_history.json"
    path.write_text(json.dumps(history), encoding="utf-8")
    manager = YouTubePublishManager(history_path=path)
    assert manager.find(part_number=1, content_type=SHORTS_CONTENT_TYPE)["youtube_video_id"] == "yEgHXZc2Gls"
    assert manager.find(part_number=1, content_type=TEN_QUESTION_CONTENT_TYPE) is None
    assert not manager.is_duplicate(1, "b" * 64, TEN_QUESTION_CONTENT_TYPE)


def test_ten_part_one_available_despite_shorts_part_one(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    history.write_text(json.dumps({
        "schema_version": 1,
        "records": [
            _record(1, SHORTS_CONTENT_TYPE, "yEgHXZc2Gls"),
            _record(25, SHORTS_CONTENT_TYPE, "", status="failed"),
            _record(26, SHORTS_CONTENT_TYPE, "c22bxuuTvd8"),
        ],
    }), encoding="utf-8")
    assert next_youtube_part_number(history_path=history, content_type=TEN_QUESTION_CONTENT_TYPE) == 1
    assert next_youtube_part_number(history_path=history) == 2
    assert json.loads(history.read_text(encoding="utf-8"))["records"][0]["youtube_video_id"] == "yEgHXZc2Gls"


# --- CLI and workflow ------------------------------------------------------

def test_cli_dry_run_uses_ten_question_resolver(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    root = tmp_path / "output" / "youtube"
    video = youtube_ten_question_video_path(1, root)
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.setattr(youtube_publisher, "_run_ffprobe", lambda path: json.loads(json.dumps(VALID_PROBE)) | {"format": {"duration": "60.0"}})
    monkeypatch.setattr(youtube_publisher, "_http_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP called")))

    main._run_publish_youtube_video(SimpleNamespace(part=1, output_root=str(root), youtube_privacy=None))
    output = capsys.readouterr().out
    assert "10-question" in output
    assert "world_general_knowledge_quiz_part_001_10_questions.mp4" in output


def test_cli_upload_forces_private_and_ten_content_type(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    root = tmp_path / "output" / "youtube"
    video = youtube_ten_question_video_path(1, root)
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    for name in youtube_publisher.SECRET_ENV_NAMES:
        monkeypatch.setenv(name, "present")
    monkeypatch.setenv(youtube_publisher.NETWORK_UPLOAD_ENV_FLAG, "true")
    monkeypatch.setattr("config.YOUTUBE_PUBLISH_ENABLED", True)
    monkeypatch.setattr("config.YOUTUBE_PUBLISH_DRY_RUN", False)
    seen = {}

    def fake_publish_once(self, part, path, manager):
        seen["content_type"] = self.content_type
        seen["privacy"] = self.privacy_status
        return {
            "success": True, "skipped": False, "needs_reconciliation": False,
            "part_number": part, "status": "uploaded", "youtube_video_id": "VIDEO",
        }

    monkeypatch.setattr(YouTubePublisher, "publish_once", fake_publish_once)
    main._run_youtube_video_upload(SimpleNamespace(part=1, output_root=str(root)))
    assert seen == {"content_type": TEN_QUESTION_CONTENT_TYPE, "privacy": "private"}


def test_workflow_uses_ten_question_commands():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "YouTube 10-Question Video Test Upload (Private)" in text
    assert "TEN_QUESTION_CONTENT_TYPE" in text
    assert "--count 10" in text or 'QUESTIONS_PER_PART: "10"' in text
    for flag in ("--render-ten-video", "--ten-question-count 10", "--youtube-ten-question-video",
                 "--publish-youtube-video", "--youtube-video-upload", "youtube_ten_question_video_path"):
        assert flag in text, flag
    assert "--render-reels" not in text
    assert "duration <= 180" not in text
    assert "at most 180 seconds" not in text
    assert "questions in script" in text or "len(questions) != 10" in text


def test_facebook_workflows_still_unchanged():
    for name in ("scheduled-world-quiz-videos.yml", "facebook-test-reel.yml", "generate-world-quiz-videos.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        if "- name: Generate next quiz Part" in text:
            fb_step = text.split("- name: Generate next quiz Part", 1)[1].split("\n      - name:", 1)[0]
            assert "--youtube-ten-question-video" not in fb_step
            assert "--youtube-video-upload" not in fb_step
        assert "--publish-content-type ten_question_video" in text or name != "scheduled-world-quiz-videos.yml"
