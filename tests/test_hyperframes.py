from pathlib import Path

from core.quiz_generator import build_quiz
from integrations import hyperframes


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