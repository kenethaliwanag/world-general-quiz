import re
from pathlib import Path

from core.quiz_generator import build_quiz
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


def test_intro_and_outro_use_progressive_word_elements(tmp_path, monkeypatch):
    questions = [
        {"id": "q1", "question": "Example?", "answer": "Example.", "category": "general", "difficulty": "easy"}
    ]
    monkeypatch.setattr(hyperframes, "OUTPUT_DIR", tmp_path / "output")
    quiz = build_quiz(1, questions)
    quiz["intro"] = ["Welcome to Quiz!", "Get ready for one question!", "This is Part 1."]
    quiz["ending"] = "How many did you get right? Comment your score!"
    project_dir, duration, timeline = hyperframes.create_composition(quiz, audio_map=None)

    html = (project_dir / "index.html").read_text(encoding="utf-8")
    assert 'intro-title-word-1' in html
    assert 'intro-title-word-3' in html
    assert 'intro-subtitle-word-1' in html
    assert 'ending-text-word-1' in html
    assert 'ending-text-word-6' in html
    assert "HOW DID YOU DO?" in html


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
