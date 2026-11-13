import json
import os
import tempfile
from config import HISTORY_FILE

def _normalize_history(history):
    if not isinstance(history, dict):
        return {"used_ids": [], "last_part": 0}
    used_ids = history.get("used_ids", [])
    if not isinstance(used_ids, list):
        used_ids = []
    used_ids = [str(item) for item in used_ids]
    used_ids = list(dict.fromkeys(used_ids))
    try:
        last_part = int(history.get("last_part", 0))
    except (TypeError, ValueError):
        last_part = 0
    return {"used_ids": used_ids, "last_part": last_part if last_part >= 0 else 0}

def load_history():
    if not HISTORY_FILE.exists():
        return {"used_ids": [], "last_part": 0}
    try:
        return _normalize_history(json.loads(HISTORY_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {"used_ids": [], "last_part": 0}

def save_history(history):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_history(history)
    fd, temp_name = tempfile.mkstemp(prefix="used_questions_", suffix=".json", dir=str(HISTORY_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, HISTORY_FILE)
    finally:
        try:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        except OSError:
            pass

def next_part_number():
    return int(load_history().get("last_part", 0)) + 1


def record_question_usage(history, question_ids, part_number):
    """Persist newly used question IDs only after a Part succeeds.

    The input history is not mutated; a normalized copy is saved and returned.

    `used_ids` stays a list of unique IDs in recency order: the first entry was
    used longest ago. An ID that is used again moves to the end, so the next
    Part recycles a different question instead of the same one.
    """
    history = _normalize_history(history)
    selected = [str(item) for item in (question_ids or [])]
    selected_ids = set(selected)
    previous = set(history["used_ids"])
    remaining = [qid for qid in history["used_ids"] if qid not in selected_ids]
    fresh = [qid for qid in selected if qid not in previous]
    reused = [qid for qid in selected if qid in previous]
    history["used_ids"] = list(dict.fromkeys(remaining + fresh + reused))
    history["last_part"] = max(int(history.get("last_part", 0)), int(part_number))
    save_history(history)
    return history


def reset_history():
    save_history({"used_ids": [], "last_part": 0})
