import json
import random
from config import QUESTIONS_FILE
from core.history_manager import (
    _normalize_history,
    load_history,
    record_question_usage,
    save_history,
)

VALID_DIFFICULTIES = {"easy", "medium", "hard"}

def load_questions():
    with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
        questions = json.load(f)
    if not isinstance(questions, list) or not questions:
        raise ValueError("Question bank is empty or invalid.")
    ids = [q.get("id") for q in questions if isinstance(q, dict)]
    if len(ids) != len(set(ids)):
        raise ValueError("Question bank contains duplicate question IDs.")
    seen = set()
    for index, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            raise ValueError(f"Question {index} is not a JSON object.")
        for field in ("id", "question", "answer", "category", "difficulty"):
            if not isinstance(question.get(field), str) or not question[field].strip():
                raise ValueError(f"Question {index} is missing a valid '{field}'.")
        if question["difficulty"].lower() not in VALID_DIFFICULTIES:
            raise ValueError(f"Question {question['id']} has invalid difficulty '{question['difficulty']}'.")
        if question["id"] in seen:
            raise ValueError(f"Duplicate question ID: {question['id']}")
        seen.add(question["id"])
    return questions

def select_questions(count=15, category=None, difficulty=None, seed=None, history=None):
    """Select unique questions, preferring never-used IDs across all Parts.

    Selected IDs are returned only as a reservation. They are not marked used
    here; the caller must persist them after a Part has completed successfully.
    """
    rng = random.Random(seed)
    all_questions = load_questions()
    candidates = [
        q for q in all_questions
        if (not category or category.lower() == "all" or q["category"].lower() == category.lower())
        and (not difficulty or difficulty.lower() == "all" or q["difficulty"].lower() == difficulty.lower())
    ]
    if len(candidates) < count:
        raise ValueError(f"Only {len(candidates)} questions match these filters; {count} required.")

    if history is None:
        history = load_history()
    history = _normalize_history(history)
    used = set(history.get("used_ids", []))
    fresh = [q for q in candidates if q["id"] not in used]

    if len(fresh) < count:
        raise ValueError(
            "No unused questions remain for these filters; "
            f"{len(fresh)} unused questions remain but {count} are required. "
            "Reset question history explicitly to intentionally reuse questions."
        )

    selected = rng.sample(fresh, count)
    return selected, False, history

from core.history_manager import record_question_usage

def record_part(part_number, question_ids=None, history=None):
    if history is None:
        history = load_history()
    if question_ids is None:
        question_ids = []
    return record_question_usage(history, question_ids, part_number)
