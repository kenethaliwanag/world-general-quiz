"""Regression tests for independent YouTube output root and Part numbering."""
import json
from pathlib import Path
from types import SimpleNamespace

import core.history_manager as history_manager
import core.question_manager as question_manager
import core.script_exporter as exporter
import main
from core.youtube_output import next_youtube_part_number, youtube_part_dir, youtube_shorts_path
from core.youtube_publish_manager import YouTubePublishManager


ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_WORKFLOW = ROOT / ".github" / "workflows" / "youtube-test-upload.yml"
FACEBOOK_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "scheduled-world-quiz-videos.yml",
    ROOT / ".github" / "workflows" / "facebook-test-reel.yml",
    ROOT / ".github" / "workflows" / "generate-world-quiz-videos.yml",
)


def _args(part=1, output_root=None, youtube_shorts=False, render_reels=True):
    return SimpleNamespace(
        count=5, category="all", difficulty="all", seed=42, part=part,
        start_part=None, total_parts=None, tts=False, render=False,
        reset_history=False, render_reels=render_reels,
        render_facebook_reels=False, facebook_reels=False,
        reels_question_count=5, facebook_reels_question_count=None,
        render_ten_video=False, render_facebook_ten_video=False,
        facebook_ten_video=False, facebook_ten_question_count=None,
        output_root=output_root, youtube_shorts=youtube_shorts,
    )


def _bank(tmp_path, monkeypatch, last_part=25):
    questions = [
        {"id": f"q{i}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, 8)
    ]
    q_file = tmp_path / "questions.json"
    q_file.write_text(json.dumps(questions), encoding="utf-8")
    h_file = tmp_path / "data" / "used_questions.json"
    h_file.parent.mkdir(parents=True, exist_ok=True)
    h_file.write_text(json.dumps({"used_ids": [f"q{i}" for i in range(1, 6)], "last_part": last_part}), encoding="utf-8")
    monkeypatch.setattr(history_manager, "HISTORY_FILE", h_file)
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", q_file)
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(exporter, "OUTPUT_DIR", tmp_path / "output")

    def fake_create(quiz, audio_map=None, content_type="full", tracker=None, output_root=None, **kwargs):
        root = Path(output_root) if output_root else main.OUTPUT_DIR
        project = root / "hyperframes" / f"part_{quiz['part']:03d}"
        if content_type == "reel":
            project = project / "reels"
        project.mkdir(parents=True, exist_ok=True)
        (project / "index.html").write_text("composition", encoding="utf-8")
        return project, 1.0, {}

    def fake_render(project_dir, part_number, output_path=None, **kwargs):
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake mp4")
        return target

    monkeypatch.setattr(main, "create_composition", fake_create)
    monkeypatch.setattr(main, "render_video", fake_render)
    return h_file


def _record(part, status="uploaded", video_id="VIDEO", content_hash="a" * 64):
    return {
        "part_number": part, "video_file_name": "short.mp4", "content_hash": content_hash,
        "content_type": "youtube_shorts", "title": "Title", "youtube_video_id": video_id,
        "upload_status": status, "privacy_status": "private",
        "created_at": "2026-01-01T00:00:00+00:00", "published_at": "2026-01-01T00:00:00+00:00",
        "errors": [],
    }


# --- Output paths ----------------------------------------------------------

def test_default_generation_preserves_facebook_paths(tmp_path, monkeypatch):
    _bank(tmp_path, monkeypatch)
    main.generate_part(1, _args(youtube_shorts=False))
    part_dir = tmp_path / "output" / "part_001"
    assert (part_dir / "script.json").is_file()
    assert (part_dir / "facebook" / "reels" / "world_general_knowledge_quiz_part_001_reel.mp4").is_file()
    assert not (tmp_path / "output" / "youtube").exists()


def test_youtube_root_writes_exclusively_there(tmp_path, monkeypatch):
    _bank(tmp_path, monkeypatch)
    root = tmp_path / "output" / "youtube"
    main.generate_part(1, _args(output_root=str(root), youtube_shorts=True))
    shorts = youtube_shorts_path(1, root)
    assert shorts.is_file()
    assert shorts == root / "part_001" / "youtube" / "shorts" / "world_general_knowledge_quiz_part_001.mp4"
    assert not (tmp_path / "output" / "part_001").exists()
    assert not any(path.name == "facebook" for path in (root / "part_001").rglob("*"))
    assert (root / "hyperframes" / "part_001" / "reels" / "index.html").is_file()


def test_shared_resolver_matches_generated_file(tmp_path, monkeypatch):
    _bank(tmp_path, monkeypatch)
    root = tmp_path / "output" / "youtube"
    main.generate_part(3, _args(part=3, output_root=str(root), youtube_shorts=True))
    assert youtube_shorts_path(3, root).is_file()
    assert youtube_part_dir(3, root).is_dir()
    assert not youtube_shorts_path(3, root).as_posix().endswith("facebook/reels/world_general_knowledge_quiz_part_003_reel.mp4")


# --- Independent Part numbering -------------------------------------------

def test_first_youtube_part_is_one_with_failed_25_preserved(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    history.write_text(json.dumps({"schema_version": 1, "records": [_record(25, "failed", "")]}), encoding="utf-8")
    assert next_youtube_part_number(history_path=history, output_root=tmp_path / "output" / "youtube") == 1
    assert json.loads(history.read_text(encoding="utf-8"))["records"][0]["part_number"] == 25


def test_next_youtube_part_is_two_after_success(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    history.write_text(
        json.dumps({"schema_version": 1, "records": [_record(25, "failed", ""), _record(1, "uploaded", "VIDEO1")]}),
        encoding="utf-8",
    )
    assert next_youtube_part_number(history_path=history) == 2


def test_failed_attempt_does_not_consume_part(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    history.write_text(json.dumps({"schema_version": 1, "records": [_record(1, "failed", "")]}), encoding="utf-8")
    assert next_youtube_part_number(history_path=history) == 1


def test_failed_record_with_video_id_blocks_reuse(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    history.write_text(json.dumps({"schema_version": 1, "records": [_record(1, "failed", "VIDEO1")]}), encoding="utf-8")
    assert next_youtube_part_number(history_path=history) == 2


def test_existing_output_directory_reserves_its_part(tmp_path):
    root = tmp_path / "output" / "youtube"
    shorts = youtube_shorts_path(1, root)
    shorts.parent.mkdir(parents=True)
    shorts.write_bytes(b"existing")
    history = tmp_path / "youtube_publish_history.json"
    history.write_text(json.dumps({"schema_version": 1, "records": []}), encoding="utf-8")
    assert next_youtube_part_number(history_path=history, output_root=root) == 2


def test_failed_part_with_existing_short_can_be_retried(tmp_path):
    root = tmp_path / "output" / "youtube"
    shorts = youtube_shorts_path(1, root)
    shorts.parent.mkdir(parents=True)
    shorts.write_bytes(b"existing")
    history = tmp_path / "youtube_publish_history.json"
    history.write_text(json.dumps({"schema_version": 1, "records": [_record(1, "failed", "")]}), encoding="utf-8")
    assert next_youtube_part_number(history_path=history, output_root=root) == 1


def test_existing_history_is_not_overwritten_by_manager(tmp_path):
    history = tmp_path / "youtube_publish_history.json"
    manager = YouTubePublishManager(history_path=history)
    manager.record(_record(25, "failed", "", content_hash="f" * 64))
    manager.record(_record(25, "uploaded", "NEWVIDEO", content_hash="e" * 64))
    records = json.loads(history.read_text(encoding="utf-8"))["records"]
    assert len(records) == 2
    assert records[0]["upload_status"] == "failed"
    assert records[1]["upload_status"] == "uploaded"


# --- Global question history / Facebook numbering -------------------------

def test_youtube_part_one_does_not_lower_facebook_part_counter(tmp_path, monkeypatch):
    h_file = _bank(tmp_path, monkeypatch, last_part=25)
    assert history_manager.next_part_number() == 26
    main.generate_part(1, _args(output_root=str(tmp_path / "output" / "youtube"), youtube_shorts=True))
    after = json.loads(h_file.read_text(encoding="utf-8"))
    assert after["last_part"] == 25
    assert set(after) == {"used_ids", "last_part"}
    assert history_manager.next_part_number() == 26


# --- Workflow / ignore rules ---------------------------------------------

def test_youtube_workflow_uses_youtube_paths_and_resolver():
    text = YOUTUBE_WORKFLOW.read_text(encoding="utf-8")
    assert "TEN_QUESTION_CONTENT_TYPE" in text
    assert "next_youtube_part_number" in text
    assert "youtube_ten_question_video_path" in text
    assert "--output-root output/youtube" in text
    assert "--render-ten-video" in text
    assert "--youtube-ten-question-video" in text
    assert '--count "$QUESTIONS_PER_PART"' in text
    assert 'QUESTIONS_PER_PART: "10"' in text
    assert "output/youtube/**" in text
    assert "facebook/reels" not in text
    assert "next_part_number()" not in text


def test_facebook_workflows_unchanged():
    for workflow in FACEBOOK_WORKFLOWS:
        text = workflow.read_text(encoding="utf-8")
        assert "--render-reels" in text
        if "- name: Generate next quiz Part" in text:
            # Facebook's generation command keeps the original output root and flags.
            fb_step = text.split("- name: Generate next quiz Part", 1)[1].split("\n      - name:", 1)[0]
            assert "--output-root" not in fb_step
            assert "--youtube-ten-question-video" not in fb_step
        assert "--youtube-video-upload" not in text or workflow.name == "scheduled-world-quiz-videos.yml"


def test_gitignore_ignores_youtube_output():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "output/youtube/*" in text
