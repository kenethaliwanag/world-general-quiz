"""Integration-style tests for one successful Part and one failed Part."""
import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import main
import core.history_manager as history_manager
import core.script_exporter as exporter
import core.question_manager as question_manager
from integrations import hyperframes


def _args(render=True):
    return SimpleNamespace(count=2, category="all", difficulty="all", seed=42,
                           part=None, start_part=None, total_parts=None,
                           tts=False, render=render, reset_history=False,
                           render_reels=False, render_facebook_reels=False,
                           facebook_reels=False, reels_question_count=2,
                           facebook_reels_question_count=None,
                           render_ten_video=False, render_facebook_ten_video=False,
                           facebook_ten_video=False, facebook_ten_question_count=None)


def _bank(tmp_path, monkeypatch):
    questions = [
        {"id": f"q{i}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, 8)
    ]
    q_file = tmp_path / "questions.json"
    q_file.write_text(__import__("json").dumps(questions), encoding="utf-8")
    h_file = tmp_path / "used.json"
    out_dir = tmp_path / "output"
    monkeypatch.setattr(history_manager, "HISTORY_FILE", h_file)
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", q_file)
    monkeypatch.setattr(main, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(exporter, "OUTPUT_DIR", out_dir)
    return history_manager.load_history(), questions


def _fake_create(quiz, audio_map=None, **kwargs):
    project_dir = Path(main.OUTPUT_DIR) / "hyperframes" / f"part_{quiz['part']:03d}"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "index.html").write_text("composition", encoding="utf-8")
    return project_dir, 1.0, {}


def test_generate_part_records_history_after_render(tmp_path, monkeypatch):
    history, _ = _bank(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "create_composition", _fake_create)
    monkeypatch.setattr(main, "render_video", lambda project_dir, part_number, output_path=None: (
        _fake_video(main.OUTPUT_DIR, part_number, output_path)
    ))
    args = _args(render=True)
    part_dir, returned_history = main.generate_part(1, args, history=history)

    assert part_dir.exists()
    assert (part_dir / "video" / "world_general_knowledge_quiz_part_001.mp4").exists()
    assert len(returned_history["used_ids"]) == 2
    assert history_manager.load_history()["used_ids"] == returned_history["used_ids"]
    assert returned_history["last_part"] == 1


def _fake_video(output_dir, part_number, output_path=None):
    if output_path is not None:
        target = Path(output_path)
    else:
        target = Path(output_dir) / f"part_{part_number:03d}" / "video" / f"world_general_knowledge_quiz_part_{part_number:03d}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fake mp4")
    return target


def test_generate_part_without_render_records_history_after_export(tmp_path, monkeypatch):
    history, _ = _bank(tmp_path, monkeypatch)
    args = _args(render=False)
    part_dir, returned_history = main.generate_part(1, args, history=history)
    assert (part_dir / "script.json").exists()
    assert len(returned_history["used_ids"]) == 2
    assert history_manager.load_history()["used_ids"] == returned_history["used_ids"]


def test_failed_render_does_not_advance_history(tmp_path, monkeypatch):
    history, _ = _bank(tmp_path, monkeypatch)
    before = history
    monkeypatch.setattr(main, "create_composition", _fake_create)

    def failing_render(project_dir, part_number):
        raise RuntimeError("render failed")

    monkeypatch.setattr(main, "render_video", failing_render)
    args = _args(render=True)

    raised = False
    try:
        main.generate_part(1, args, history=before)
    except RuntimeError as exc:
        raised = True
        assert "render failed" in str(exc)
    assert raised
    assert history_manager.load_history()["used_ids"] == before.get("used_ids", [])


def test_tts_failure_does_not_advance_history(tmp_path, monkeypatch):
    history, _ = _bank(tmp_path, monkeypatch)

    class FailingKokoroTTS:
        def __init__(self, *args, **kwargs):
            pass
        def synthesize(self, text, output_path):
            raise RuntimeError("connection failed")
        def measure(self, output_path):
            return 1.0

    monkeypatch.setattr(main, "KokoroTTS", FailingKokoroTTS)
    args = SimpleNamespace(count=2, category="all", difficulty="all", seed=42,
                           part=None, start_part=None, total_parts=None,
                           tts=True, render=False, reset_history=False)

    raised = False
    try:
        main.generate_part(1, args, history=history)
    except SystemExit as exc:
        raised = True
        assert "connection failed" in str(exc)
    assert raised
    assert history_manager.load_history()["used_ids"] == history.get("used_ids", [])


def test_successive_parts_do_not_reuse_question_ids(tmp_path, monkeypatch):
    history, _ = _bank(tmp_path, monkeypatch)
    before = history
    monkeypatch.setattr(main, "create_composition", _fake_create)
    monkeypatch.setattr(main, "render_video", lambda project_dir, part_number, output_path=None: _fake_video(main.OUTPUT_DIR, part_number, output_path))

    first_dir, first_history = main.generate_part(1, _args(render=True), history=before)
    second_dir, second_history = main.generate_part(2, _args(render=True), history=first_history)

    assert (first_dir / "script.json").exists()
    assert (second_dir / "script.json").exists()
    assert len(second_history["used_ids"]) == 4
    first_ids = {question["id"] for question in __import__("json").loads((first_dir / "script.json").read_text())["questions"]}
    second_ids = {question["id"] for question in __import__("json").loads((second_dir / "script.json").read_text())["questions"]}
    assert not first_ids.intersection(second_ids)
    assert history_manager.load_history()["last_part"] == 2


def test_generate_part_renders_ten_question_facebook_video(tmp_path, monkeypatch):
    import json
    questions = [
        {"id": f"q{i}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, 16)
    ]
    q_file = tmp_path / "questions.json"
    q_file.write_text(json.dumps(questions), encoding="utf-8")
    h_file = tmp_path / "used.json"
    out_dir = tmp_path / "output"
    import core.history_manager as history_manager
    import core.question_manager as question_manager
    import core.script_exporter as exporter
    monkeypatch.setattr(history_manager, "HISTORY_FILE", h_file)
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", q_file)
    monkeypatch.setattr(main, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(exporter, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(main, "create_composition", _fake_create)
    monkeypatch.setattr(main, "render_video", lambda project_dir, part_number, output_path=None: _fake_video(main.OUTPUT_DIR, part_number, output_path))
    args = SimpleNamespace(count=10, category="all", difficulty="all", seed=42,
                           part=None, start_part=None, total_parts=None,
                           tts=False, render=True, reset_history=False,
                           render_reels=False, render_facebook_reels=False,
                           facebook_reels=False, reels_question_count=2,
                           facebook_reels_question_count=None,
                           render_ten_video=True, render_facebook_ten_video=False,
                           facebook_ten_video=False, facebook_ten_question_count=10)
    history = history_manager.load_history()
    part_dir, returned_history = main.generate_part(1, args, history=history)
    assert (part_dir / "facebook" / "videos" / "world_general_knowledge_quiz_part_001_10_questions.mp4").exists()
    assert (part_dir / "facebook" / "videos" / "script.json").exists()


def test_narration_speed_is_slower_for_page_video_but_not_for_the_reel(tmp_path, monkeypatch):
    import config
    import json

    questions = [
        {"id": f"q{i}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, 16)
    ]
    q_file = tmp_path / "questions.json"
    q_file.write_text(json.dumps(questions), encoding="utf-8")
    h_file = tmp_path / "used.json"
    out_dir = tmp_path / "output"
    monkeypatch.setattr(history_manager, "HISTORY_FILE", h_file)
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", q_file)
    monkeypatch.setattr(main, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(exporter, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(main, "create_composition", _fake_create)
    monkeypatch.setattr(main, "render_video", lambda project_dir, part_number, output_path=None: (
        _fake_video(main.OUTPUT_DIR, part_number, output_path)
    ))

    speeds = []

    class RecordingTTS:
        def __init__(self, *args, **kwargs):
            speeds.append(kwargs.get("speed"))
        def synthesize(self, text, output_path):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"fake")
            return Path(output_path)
        def measure(self, output_path):
            return 1.0

    monkeypatch.setattr(main, "KokoroTTS", RecordingTTS)
    args = SimpleNamespace(count=15, category="all", difficulty="all", seed=42,
                           part=None, start_part=None, total_parts=None,
                           tts=True, render=True, reset_history=False,
                           render_reels=True, render_facebook_reels=False,
                           facebook_reels=False, reels_question_count=5,
                           facebook_reels_question_count=None,
                           render_ten_video=True, render_facebook_ten_video=False,
                           facebook_ten_video=False, facebook_ten_question_count=10)
    main.generate_part(1, args, history=history_manager.load_history())

    # Full part, Reel, 10-question Page Video.
    assert speeds == [config.TTS_SPEED, config.TTS_SPEED_REEL, config.TTS_SPEED]
    assert config.TTS_SPEED < 1.0
    assert config.TTS_SPEED_REEL == 1.0


def test_failed_publish_exits_non_zero(tmp_path, monkeypatch):
    import config
    from integrations.facebook_publisher import FacebookPublisher

    part_dir = tmp_path / "output" / "part_001"
    videos_dir = part_dir / "facebook" / "videos"
    videos_dir.mkdir(parents=True)
    (videos_dir / "world_general_knowledge_quiz_part_001_10_questions.mp4").write_bytes(b"video")
    (part_dir / "script.json").write_text(
        '{"title": "World General Knowledge Quiz", "part": 1}', encoding="utf-8"
    )
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(config, "FACEBOOK_PUBLISH_ENABLED", True)
    monkeypatch.setattr(config, "FACEBOOK_PUBLISH_DRY_RUN", False)
    monkeypatch.setattr(
        FacebookPublisher,
        "publish_ten_question_video",
        lambda *args, **kwargs: {"success": False, "part_number": 1, "errors": ["preflight failed"]},
    )
    args = SimpleNamespace(part=1, publish_content_type="ten_question_video")

    with pytest.raises(SystemExit) as excinfo:
        main._run_publish_reel(args, dry_run=False)
    assert excinfo.value.code == 1
