import re
from pathlib import Path

import pytest

from core.quiz_generator import build_quiz
from core.script_exporter import export_srt
from integrations import hyperframes


def _elements(html):
    """Map element id -> (start, duration) for every clip/audio element."""
    found = {}
    pattern = r'<div id="([^"]+)"[^>]*?data-start="([\d.]+)"[^>]*?data-duration="([\d.]+)"'
    for match in re.finditer(pattern, html):
        found[match.group(1)] = (float(match.group(2)), float(match.group(3)))
    audio_pattern = r'<audio id="([^"]+)"[^>]*?data-start="([\d.]+)"[^>]*?data-duration="([\d.]+)"'
    for match in re.finditer(audio_pattern, html):
        found[match.group(1)] = (float(match.group(2)), float(match.group(3)))
    return found


def _questions(count):
    return [
        {"id": f"q{i}", "question": f"Question {i}?", "answer": f"Answer {i}.",
         "category": "general", "difficulty": "easy"}
        for i in range(1, count + 1)
    ]


def _css(html, selector):
    """Return the declarations of one CSS rule, e.g. '.tracker-layout .ending'."""
    match = re.search(re.escape(selector) + r"\{([^}]*)\}", html)
    assert match, f"CSS rule {selector} not found"
    declarations = {}
    for part in match.group(1).split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            declarations[key.strip()] = value.strip()
    return declarations


def _px(rule, key):
    return int(rule[key].replace("px", ""))


def test_intro_and_outro_use_progressive_word_elements(tmp_path, monkeypatch):
    questions = [
        {"id": "q1", "question": "Example?", "answer": "Example.", "category": "general", "difficulty": "easy"}
    ]
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, questions)
    quiz["intro"] = ["Welcome to Quiz!", "Get ready for one question!", "This is Part 1."]
    quiz["ending_lines"] = ["How did you do?", "How many did you get right? Comment your score!"]
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None)

    html = (project_dir / "index.html").read_text(encoding="utf-8")
    assert 'intro-title-word-1' in html
    assert 'intro-title-word-3' in html
    assert 'intro-subtitle-word-1' in html
    assert 'ending-text-word-1' in html
    assert 'ending-text-word-6' in html
    assert "How did you do?" in html


def test_tracker_renders_one_answer_board_with_ten_slots(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(10))
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None, tracker=True)
    html = (project_dir / "index.html").read_text(encoding="utf-8")

    # Exactly one board, numbered 1 to 10.
    assert 'id="root" class="tracker-layout"' in html
    assert html.count('class="clip slot-num"') == 10
    assert html.count('class="clip slot-num-active"') == 10
    assert html.count('class="clip slot-box slot-box-pending"') == 10
    assert html.count('class="clip slot-box slot-box-active"') == 10
    assert html.count('class="clip slot-box slot-box-done"') == 10
    for number in range(1, 11):
        assert f'id="slot-num-{number}"' in html
        assert f'id="slot-box-done-{number}"' in html
        assert f">{number})</div>" in html
    # The old side tracker must not exist any more.
    assert "tracker-number-" not in html
    assert "tracker-answer-" not in html


def test_tracker_board_is_two_columns_with_answer_beside_number(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(10))
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None, tracker=True)
    html = (project_dir / "index.html").read_text(encoding="utf-8")

    left_column, right_column = hyperframes.SLOT_COLUMNS
    assert left_column[0] < right_column[0]
    for number in range(1, 6):
        assert f'id="slot-num-{number}"' in html
        assert f"left:{left_column[0]}px" in html
    for number in range(6, 11):
        assert f'id="slot-num-{number}"' in html
        assert f"left:{right_column[0]}px" in html
    # Answers live in the slot box that sits beside the number.
    assert ">Answer 1.</div>" in html
    assert ">Answer 10.</div>" in html


def test_tracker_answers_stay_visible_and_active_slot_is_highlighted(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(10))
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None, tracker=True)
    html = (project_dir / "index.html").read_text(encoding="utf-8")
    elements = _elements(html)

    first_answer_start = elements["slot-box-done-1"][0]
    last_answer_start = elements["slot-box-done-10"][0]
    assert first_answer_start < last_answer_start
    # Every revealed answer stays on screen until the quiz ends.
    assert elements["slot-box-done-1"][0] + elements["slot-box-done-1"][1] > last_answer_start
    # The active number is highlighted only while its question runs.
    assert elements["slot-num-active-3"][0] < elements["slot-num-active-3"][0] + elements["slot-num-active-3"][1]
    assert elements["slot-box-active-3"][0] < elements["slot-box-done-3"][0]
    assert elements["slot-box-pending-3"][0] < elements["slot-box-active-3"][0]


def test_tracker_countdown_bar_is_synced_with_tick_sfx(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(10))
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None, tracker=True)
    html = (project_dir / "index.html").read_text(encoding="utf-8")
    elements = _elements(html)

    for number in range(1, 11):
        for second in range(hyperframes.COUNTDOWN_SECONDS, 0, -1):
            fill = elements[f"q{number}-timer-{second}"]
            tick = elements[f"sfx-q{number}-{second}-tick"]
            assert fill[0] == tick[0]
            assert elements[f"q{number}-countdown-{second}"][0] == tick[0]
        assert elements[f"q{number}-timer-track"][0] == elements[f"q{number}-timer-{hyperframes.COUNTDOWN_SECONDS}"][0]


def test_tracker_question_stays_visible_until_the_next_question(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(10), content_type="ten_question_video")
    project_dir, duration, timeline = hyperframes.create_composition(
        quiz, audio_map=None, content_type="ten_question_video", tracker=True
    )
    html = (project_dir / "index.html").read_text(encoding="utf-8")
    elements = _elements(html)

    for number in range(1, 11):
        start, visible = elements[f"q{number}-question"]
        # The label, the difficulty pill and the question share one lifetime.
        assert elements[f"q{number}-label"][0] == start
        assert elements[f"q{number}-difficulty"][1] == visible
        # Still on screen while the correct answer is revealed.
        assert start + visible > elements[f"slot-box-done-{number}"][0]
        if number < 10:
            # Replaced exactly when the next question starts.
            assert start + visible == pytest.approx(elements[f"q{number + 1}-question"][0])
        else:
            # The last question is replaced by the outro.
            assert start + visible == pytest.approx(elements["ending-eyebrow-word-1"][0])


def test_full_video_question_still_clears_before_the_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(15))
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None)
    html = (project_dir / "index.html").read_text(encoding="utf-8")
    elements = _elements(html)

    for number in range(1, 16):
        start, visible = elements[f"q{number}-question"]
        # The 15-question format keeps its big centred answer card, so the
        # question still clears when the answer appears.
        assert start + visible == pytest.approx(elements[f"q{number}-answer-label"][0])


def test_tracker_outro_text_is_large_centered_and_inside_the_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(10), content_type="ten_question_video")
    project_dir, duration, timeline = hyperframes.create_composition(
        quiz, audio_map=None, content_type="ten_question_video", tracker=True
    )
    html = (project_dir / "index.html").read_text(encoding="utf-8")

    ending = _css(html, ".tracker-layout .ending")
    assert _px(ending, "font-size") >= 92
    top = _px(ending, "top")
    height = _px(ending, "height")
    assert top + height <= hyperframes.VIDEO_HEIGHT
    # Centred in the frame, both ways.
    assert abs((top + height / 2) - hyperframes.VIDEO_HEIGHT / 2) <= 60
    assert _px(ending, "left") == hyperframes.CONTENT_LEFT_PX
    assert _px(ending, "width") == hyperframes.CONTENT_WIDTH_PX

    # Nothing else shares the ending block.
    for selector in (".tracker-layout .eyebrow", ".tracker-layout .cta", ".tracker-layout .cta-sub"):
        rule = _css(html, selector)
        rule_top = _px(rule, "top")
        rule_bottom = rule_top + _px(rule, "height")
        assert rule_bottom <= top or rule_top >= top + height

    # The Part badge no longer overlaps the ending text.
    part = _css(html, ".tracker-layout .ending-partline")
    assert _px(part, "top") >= top + height
    assert _px(part, "top") + _px(part, "height") <= hyperframes.VIDEO_HEIGHT


def test_reel_keeps_bare_question_text_for_the_90_second_limit():
    quiz = build_quiz(1, _questions(5), content_type="reel")
    assert quiz["questions"][0]["spoken"] == quiz["questions"][0]["question"]
    assert quiz["intro"][2] == "This is Part 1. Can you get all 5 right?"


def test_full_video_and_reel_layouts_are_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(15))
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None)
    html = (project_dir / "index.html").read_text(encoding="utf-8")

    assert 'id="slot-num-' not in html
    assert 'id="slot-box-' not in html
    assert 'id="q1-timer-' not in html
    assert 'id="root" class=""' in html
    assert html.count('class="clip eyebrow answer-label"') == 15
    assert html.count('class="clip answer"') == 15
    assert html.count('class="clip question"') == 15

    reel_project, reel_duration, _ = hyperframes.create_composition(
        build_quiz(1, _questions(5)), audio_map=None, content_type="reel"
    )
    reel_html = (reel_project / "index.html").read_text(encoding="utf-8")
    assert 'id="slot-num-' not in reel_html
    assert reel_html.count('class="clip answer"') == 5


def test_every_visible_line_is_narrated(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, _questions(10), content_type="ten_question_video")
    project_dir, duration, timeline = hyperframes.create_composition(
        quiz, audio_map=None, content_type="ten_question_video", tracker=True
    )
    html = (project_dir / "index.html").read_text(encoding="utf-8")

    # Intro: title, subtitle, part line and the challenge hook each get a line.
    assert len(quiz["intro"]) == 4
    assert 'id="intro-title-word-1"' in html
    assert 'id="intro-subtitle-word-1"' in html
    assert 'id="intro-partline-word-1"' in html
    assert 'id="intro-hook-word-1"' in html

    # Outro: result eyebrow, score line, comment prompt, share/follow line.
    assert 'id="ending-eyebrow-word-1"' in html
    assert 'id="ending-text-word-1"' in html
    assert 'id="ending-cta"' in html
    assert 'id="ending-cta-sub"' in html

    # The question label and the difficulty shown on screen are spoken too.
    first = quiz["questions"][0]
    assert first["spoken"] == "Question 1, easy. Question 1?"
    assert first["spoken_answer"] == "Answer 1 is the correct answer."


def test_lines_are_timed_to_their_own_narration_clips(tmp_path, monkeypatch):
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(hyperframes, "measure_audio_duration", lambda path: 2.0)
    quiz = build_quiz(1, _questions(10), content_type="ten_question_video")
    audio_map = {}
    for key in [f"intro_{index}" for index in range(1, 5)] + [f"ending_{index}" for index in range(1, 5)]:
        path = tmp_path / f"{key}.mp3"
        path.write_bytes(b"fake")
        audio_map[key] = path

    project_dir, duration, timeline = hyperframes.create_composition(
        quiz, audio_map=audio_map, content_type="ten_question_video", tracker=True
    )
    html = (project_dir / "index.html").read_text(encoding="utf-8")
    elements = _elements(html)

    # Every line starts when its own clip starts, and each line is 2.0s + padding.
    assert elements["intro-title-word-1"][0] == 0.0
    assert elements["intro-subtitle-word-1"][0] == pytest.approx(2.5)
    assert elements["intro-partline-word-1"][0] == pytest.approx(5.0)
    assert elements["intro-hook-word-1"][0] == pytest.approx(7.5)
    assert elements["audio-intro_4"][0] == pytest.approx(7.5)

    # The call to action appears exactly when it is spoken.
    assert elements["ending-cta"][0] == elements["audio-ending_3"][0]
    assert elements["ending-cta-sub"][0] == elements["audio-ending_4"][0]
    assert elements["ending-eyebrow-word-1"][0] == elements["audio-ending_1"][0]


def test_srt_cues_follow_the_spoken_script(tmp_path):
    quiz = build_quiz(1, _questions(3), content_type="ten_question_video")
    path = export_srt(quiz, tmp_path, {})
    srt = path.read_text(encoding="utf-8")
    for line in quiz["intro"]:
        assert line in srt
    for line in quiz["ending_lines"]:
        assert line in srt
    assert quiz["questions"][0]["spoken"] in srt
    assert quiz["questions"][0]["spoken_answer"] in srt


def _fake_which(name):
    return name if name in {"npx", "npx.cmd", "ffmpeg"} else None


def _fake_render_commands(calls):
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1] == "hyperframes":
            raw = Path(command[command.index("--output") + 1])
            assert raw.is_absolute()
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(b"raw")
        else:
            raw = Path(command[command.index("-i") + 1])
            normalized = Path(command[-1])
            assert raw.is_absolute() and raw.is_file()
            assert normalized.is_absolute()
            normalized.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_bytes(b"normalized")

    return fake_run


def test_relative_render_output_is_resolved_before_subprocess(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    project = tmp_path / "project" / "part_001" / "reels"
    project.mkdir(parents=True)
    relative = Path("output/youtube/part_001/youtube/shorts/part_001.mp4")
    calls = []
    validated = []

    monkeypatch.chdir(repo)
    monkeypatch.setattr(hyperframes.shutil, "which", _fake_which)
    monkeypatch.setattr(hyperframes.subprocess, "run", _fake_render_commands(calls))
    monkeypatch.setattr(hyperframes, "_validate_rendered_video", lambda path: validated.append(Path(path)))

    result = hyperframes.render_video(project, 1, output_path=relative)

    raw = repo / relative.with_name("part_001.raw.mp4")
    normalized = repo / relative.with_name("part_001.normalized.mp4")
    assert result == repo / relative
    assert result.is_absolute() and result.is_file()
    assert not (project / "output").exists(), "HyperFrames must not create a nested output directory"
    hyper_calls = [call for call in calls if call[1] == "hyperframes"]
    ffmpeg_calls = [call for call in calls if call[0] == "ffmpeg"]
    assert len(hyper_calls) == 1 and len(ffmpeg_calls) == 1
    assert Path(hyper_calls[0][hyper_calls[0].index("--output") + 1]) == raw
    assert Path(ffmpeg_calls[0][ffmpeg_calls[0].index("-i") + 1]) == raw
    assert Path(ffmpeg_calls[0][-1]) == normalized
    assert validated == [raw, normalized, repo / relative]


def test_default_render_output_path_is_unchanged(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    project = tmp_path / "project"
    project.mkdir()
    calls = []
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(hyperframes.shutil, "which", _fake_which)
    monkeypatch.setattr(hyperframes.subprocess, "run", _fake_render_commands(calls))
    monkeypatch.setattr(hyperframes, "_validate_rendered_video", lambda path: None)

    result = hyperframes.render_video(project, 1)

    assert result == output_dir / "part_001" / "video" / "world_general_knowledge_quiz_part_001.mp4"
    assert result.is_file()
