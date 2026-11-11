from datetime import datetime, timezone
from config import AUDIO_PADDING_SECONDS, COUNTDOWN_SECONDS, ENDING_MESSAGE, QUIZ_TITLE

INTRO_LINE_MIN_SECONDS = 2.0
ENDING_LINE_MIN_SECONDS = 2.0
QUESTION_MIN_SECONDS = 3.5
ANSWER_MIN_SECONDS = 3.0
DEFAULT_INTRO_SECONDS = 8.0
DEFAULT_ENDING_SECONDS = 6.0


def line_duration(audio_duration, minimum):
    """Duration of a narrated line: its clip plus padding, never below the minimum."""
    if audio_duration is None:
        return minimum
    return max(minimum, float(audio_duration) + AUDIO_PADDING_SECONDS)


def plan_line_durations(lines, audio_durations, prefix, minimum, legacy_total):
    """Per-line durations: each line's own clip when present, else a share of the legacy total."""
    audio_durations = audio_durations or {}
    word_counts = [max(len(line.split()), 1) for line in lines]
    total_words = sum(word_counts) or 1
    durations = []
    for index in range(len(lines)):
        audio_duration = audio_durations.get(f"{prefix}_{index + 1}")
        if audio_duration is not None:
            durations.append(line_duration(audio_duration, minimum))
        else:
            durations.append(legacy_total * word_counts[index] / total_words)
    return durations


def spoken_question(item, label=True, difficulty=False):
    """Narration for a question: the label and difficulty shown on screen are spoken too."""
    if not label:
        return item["question"]
    prefix = f"Question {item['number']}"
    if difficulty:
        prefix += f", {item['difficulty']}"
    return f"{prefix}. {item['question']}"


def spoken_answer(item):
    answer = str(item["answer"]).strip().rstrip(".!?")
    return f"{answer} is the correct answer."


def narration_style(content_type):
    """The Reel keeps the bare question text so it stays inside the 90 second limit."""
    if content_type == "reel":
        return {"label": False, "difficulty": False}
    if content_type.startswith("ten_question"):
        return {"label": True, "difficulty": True}
    return {"label": True, "difficulty": False}


def build_quiz(part_number, questions, content_type="full"):
    question_count = len(questions)
    style = narration_style(content_type)
    if content_type == "reel":
        part_line = f"This is Part {part_number}. Can you get all {question_count} right?"
    else:
        part_line = (
            f"This is Part {part_number}. If you answer {question_count} out of {question_count}, "
            "you are exceptional!"
        )
    intro = [
        f"Welcome to the {QUIZ_TITLE}!",
        f"How well do you know these {question_count} world general knowledge questions?",
        part_line,
    ]
    ending_lines = ["How did you do?", ENDING_MESSAGE]
    if content_type.startswith("ten_question"):
        intro.append(f"Can you get all {question_count} correct?")
        ending_lines = [
            "How did you do?",
            "How many did you get right?",
            "Comment your score out of 10!",
            "Share with friends and follow for more quizzes!",
        ]

    items = []
    for number, question in enumerate(questions, 1):
        item = {
            "number": number,
            "id": question["id"],
            "question": question["question"],
            "answer": question["answer"],
            "category": question["category"],
            "difficulty": question["difficulty"],
            "countdown_seconds": COUNTDOWN_SECONDS,
        }
        item["spoken"] = spoken_question(item, **style)
        item["spoken_answer"] = spoken_answer(item)
        items.append(item)

    return {
        "title": QUIZ_TITLE,
        "part": part_number,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "intro": intro,
        "countdown_seconds": COUNTDOWN_SECONDS,
        "questions": items,
        "ending": " ".join(ending_lines),
        "ending_lines": ending_lines,
    }

def format_text_script(quiz):
    lines = ["=== INTRO ===", *quiz["intro"], ""]
    for item in quiz["questions"]:
        lines += [
            f"=== QUESTION {item['number']} ===",
            f"Question: {item['question']}",
            f"Spoken: {item['spoken']}",
            f"(Wait {item['countdown_seconds']} seconds)",
            f"Answer: {item['answer']}",
            f"Spoken answer: {item['spoken_answer']}",
            ""
        ]
    lines += ["=== ENDING ===", *quiz["ending_lines"], ""]
    return "\n".join(lines)
