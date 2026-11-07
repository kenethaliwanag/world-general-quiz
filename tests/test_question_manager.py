"""Tests for question selection and duplicate prevention."""
import json

import core.history_manager as history_manager
import core.question_manager as question_manager


def _write_bank(tmp_path, questions):
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(questions), encoding="utf-8")
    return path


def _questions():
    return [
        {"id": f"q{i}", "question": f"Question {i}?", "answer": f"Answer {i}.", "category": "general", "difficulty": "easy"}
        for i in range(1, 8)
    ]


def test_load_questions_rejects_duplicates(tmp_path, monkeypatch):
    path = _write_bank(tmp_path, [{"id": "q1", "question": "A?", "answer": "B", "category": "x", "difficulty": "easy"},
                                 {"id": "q1", "question": "C?", "answer": "D", "category": "x", "difficulty": "easy"}])
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", path)
    try:
        question_manager.load_questions()
        raised = False
    except ValueError as exc:
        raised = True
        assert "duplicate" in str(exc).lower()
    assert raised


def test_select_questions_does_not_mark_history(tmp_path, monkeypatch):
    path = _write_bank(tmp_path, _questions())
    history_path = tmp_path / "used.json"
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", path)
    monkeypatch.setattr(history_manager, "HISTORY_FILE", history_path)

    history = {"used_ids": ["q1", "q2"], "last_part": 1}
    selected, pool_reset, returned_history = question_manager.select_questions(2, "all", "all", 1, history=history)

    assert len(selected) == 2
    assert pool_reset is False
    assert {q["id"] for q in selected}.isdisjoint({"q1", "q2"})
    assert not history_path.exists()


def test_select_questions_no_duplicates_within_part(tmp_path, monkeypatch):
    path = _write_bank(tmp_path, _questions())
    history_path = tmp_path / "used.json"
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", path)
    monkeypatch.setattr(history_manager, "HISTORY_FILE", history_path)

    selected, _, _ = question_manager.select_questions(4, "all", "all", 2)
    ids = [q["id"] for q in selected]
    assert len(ids) == len(set(ids))


def test_select_questions_filters_category(tmp_path, monkeypatch):
    questions = _questions()
    questions[0]["category"] = "science"
    questions[1]["category"] = "history"
    path = _write_bank(tmp_path, questions)
    history_path = tmp_path / "used.json"
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", path)
    monkeypatch.setattr(history_manager, "HISTORY_FILE", history_path)

    selected, _, _ = question_manager.select_questions(1, "science", "all", 1)
    assert selected[0]["category"] == "science"


def test_select_questions_raises_when_pool_is_exhausted(tmp_path, monkeypatch):
    path = _write_bank(tmp_path, _questions()[:3])
    history_path = tmp_path / "used.json"
    monkeypatch.setattr(question_manager, "QUESTIONS_FILE", path)
    monkeypatch.setattr(history_manager, "HISTORY_FILE", history_path)
    history_path.write_text('{"used_ids":["q1","q2"], "last_part":1}', encoding="utf-8")

    raised = False
    try:
        question_manager.select_questions(2, "all", "all", 1, history=history_manager.load_history())
    except ValueError as exc:
        raised = True
        assert "No unused questions remain" in str(exc)
    assert raised
