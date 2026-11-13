import json
import random
from config import (
    COMPARISON_TARGET_PER_PART,
    MAX_COMPARISONS_PER_PART,
    QUESTIONS_FILE,
)
from core.history_manager import (
    _normalize_history,
    load_history,
    record_question_usage,
    save_history,
)
from core.question_bank import build_generated_questions

VALID_DIFFICULTIES = {"easy", "medium", "hard"}
COMPARISON_FAMILY_PREFIX = "cmp-"


def _family(question_id):
    """The template a question came from, used to spread a Part across formats."""
    return question_id.split("--", 1)[0] if "--" in question_id else "curated"


def _is_comparison(question_id):
    """Comparison questions pair two entities; everything else is a single fact."""
    return _family(question_id).startswith(COMPARISON_FAMILY_PREFIX)


_BANK = {}


def load_questions():
    """The curated questions plus every question generated from the seed data."""
    bank_key = str(QUESTIONS_FILE)
    if bank_key in _BANK:
        return _BANK[bank_key]
    with QUESTIONS_FILE.open("r", encoding="utf-8") as f:
        curated = json.load(f)
    if not isinstance(curated, list) or not curated:
        raise ValueError("Question bank is empty or invalid.")

    # A generated question that repeats a curated one is dropped, so the same
    # question never shows up twice in a Part.
    seen_texts = {q["question"].strip().lower() for q in curated if isinstance(q, dict) and isinstance(q.get("question"), str)}
    generated = []
    for question in build_generated_questions():
        text = question["question"].strip().lower()
        if text in seen_texts:
            continue
        seen_texts.add(text)
        generated.append(question)

    questions = list(curated) + generated
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
    _BANK[bank_key] = questions
    return questions

def _spread(rng, candidates, count, age=None):
    """Pick questions across as many families as possible.

    A Part should not be fifteen comparison questions in a row, so the sample
    takes one question per family before it takes a second from any family.
    When `age` is given the candidates are taken oldest first.
    """
    families = {}
    for question in candidates:
        families.setdefault(_family(question["id"]), []).append(question)
    for bucket in families.values():
        if age is None:
            rng.shuffle(bucket)
        else:
            bucket.sort(key=lambda question: (age.get(question["id"], 0), question["id"]))
    if age is None:
        order = sorted(families)
        rng.shuffle(order)
    else:
        order = sorted(families, key=lambda family: (age.get(families[family][0]["id"], 0), family))

    selected = []
    while len(selected) < count:
        progressed = False
        for family in order:
            bucket = families[family]
            if not bucket:
                continue
            # An age sorted bucket is oldest first, so take from the front.
            selected.append(bucket.pop(0) if age is not None else bucket.pop())
            progressed = True
            if len(selected) == count:
                break
        if not progressed:
            break
    return selected

def select_questions(count=15, category=None, difficulty=None, seed=None, history=None):
    """Select unique questions for one Part.

    The Part keeps its general-knowledge character: the target is 13
    single-entity questions plus 2 comparisons, and never more than
    MAX_COMPARISONS_PER_PART comparisons.

    Priority order:
    1. fresh single-entity questions,
    2. recycled single-entity questions, least recently used first,
    3. comparison questions.

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
    # used_ids is kept in recency order: the first entry was used longest ago.
    age = {qid: index for index, qid in enumerate(history["used_ids"])}

    single_entity = [q for q in candidates if not _is_comparison(q["id"])]
    comparison = [q for q in candidates if _is_comparison(q["id"])]

    comparison_target = min(COMPARISON_TARGET_PER_PART, MAX_COMPARISONS_PER_PART)
    single_target = max(0, count - comparison_target)

    chosen = []

    # Tier 1 - fresh single-entity questions.
    fresh_single = [q for q in single_entity if q["id"] not in used]
    chosen += _spread(rng, fresh_single, single_target)

    # Tier 2 - recycled single-entity questions, least recently used first.
    if len(chosen) < single_target:
        recycled_single = sorted(
            (q for q in single_entity if q["id"] in used),
            key=lambda q: (age.get(q["id"], 0), q["id"]),
        )
        chosen += _spread(rng, recycled_single, single_target - len(chosen), age=age)

    # Tier 3 - comparison questions, up to the target.
    comparison_budget = min(comparison_target, count - len(chosen))
    picked_comparisons = _spread(
        rng, [q for q in comparison if q["id"] not in used], comparison_budget)
    if len(picked_comparisons) < comparison_budget:
        recycled_comparisons = sorted(
            (q for q in comparison if q["id"] in used),
            key=lambda q: (age.get(q["id"], 0), q["id"]),
        )
        picked_comparisons += _spread(
            rng, recycled_comparisons, comparison_budget - len(picked_comparisons), age=age)
    chosen += picked_comparisons

    # Fill the rest with more single-entity questions before more comparisons.
    if len(chosen) < count:
        taken = {q["id"] for q in chosen}
        spare = [q for q in single_entity if q["id"] not in taken]
        chosen += _spread(rng, [q for q in spare if q["id"] not in used], count - len(chosen))
        if len(chosen) < count:
            taken = {q["id"] for q in chosen}
            spare = [q for q in single_entity if q["id"] not in taken]
            chosen += _spread(
                rng,
                sorted((q for q in spare if q["id"] in used),
                       key=lambda q: (age.get(q["id"], 0), q["id"])),
                count - len(chosen),
                age=age,
            )

    # Last resort: more comparisons, never above the maximum.
    if len(chosen) < count:
        room = min(count - len(chosen), MAX_COMPARISONS_PER_PART - len(picked_comparisons))
        if room > 0:
            taken = {q["id"] for q in chosen}
            spare = [q for q in comparison if q["id"] not in taken]
            chosen += _spread(rng, spare, room)

    if len(chosen) < count:
        raise ValueError(
            f"Only {len(chosen)} eligible questions are available for a Part of {count} "
            f"with at most {MAX_COMPARISONS_PER_PART} comparison questions."
        )

    pool_reset = any(q["id"] in used for q in chosen)
    return chosen, pool_reset, history

from core.history_manager import record_question_usage

def record_part(part_number, question_ids=None, history=None):
    if history is None:
        history = load_history()
    if question_ids is None:
        question_ids = []
    return record_question_usage(history, question_ids, part_number)
