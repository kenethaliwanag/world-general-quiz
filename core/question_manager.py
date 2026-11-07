import json
import random
from config import QUESTIONS_FILE
from core.history_manager import load_history, save_history

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

def select_questions(count=15, category=None, difficulty=None, seed=None):
    """Select unique questions, preferring never-used IDs across all Parts."""
    rng = random.Random(seed)
    all_questions = load_questions()
    candidates = [
        q for q in all_questions
        if (not category or category.lower() == "all" or q["category"].lower() == category.lower())
        and (not difficulty or difficulty.lower() == "all" or q["difficulty"].lower() == difficulty.lower())
    ]
    if len(candidates) < count:
        raise ValueError(f"Only {len(candidates)} questions match these filters; {count} required.")

    history = load_history()
    used = set(history.get("used_ids", []))
    fresh = [q for q in candidates if q["id"] not in used]
    pool_reset = False
    if len(fresh) < count:
        # Exhausted the filtered pool: start a new cycle rather than failing.
        fresh = candidates
        pool_reset = True

    selected = rng.sample(fresh, count)
    history["used_ids"] = list(dict.fromkeys(history.get("used_ids", []) + [q["id"] for q in selected]))
    save_history(history)
    return selected, pool_reset

def record_part(part_number):
    history = load_history()
    history["last_part"] = max(int(history.get("last_part", 0)), int(part_number))
    save_history(history)
