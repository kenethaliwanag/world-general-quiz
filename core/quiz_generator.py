from datetime import datetime, timezone
from config import QUIZ_TITLE, COUNTDOWN_SECONDS, ENDING_MESSAGE

def build_quiz(part_number, questions):
    question_count = len(questions)
    intro = [
        QUIZ_TITLE,
        f"How well do you know these {question_count} world general knowledge questions?",
        f"This is Part {part_number}. If you answer {question_count} out of {question_count}, you are exceptional!"
    ]
    ending = ENDING_MESSAGE
    return {
        "title": QUIZ_TITLE,
        "part": part_number,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "intro": intro,
        "countdown_seconds": COUNTDOWN_SECONDS,
        "questions": [
            {
                "number": i,
                "id": q["id"],
                "question": q["question"],
                "answer": q["answer"],
                "category": q["category"],
                "difficulty": q["difficulty"],
                "countdown_seconds": COUNTDOWN_SECONDS
            }
            for i, q in enumerate(questions, 1)
        ],
        "ending": ending
    }

def format_text_script(quiz):
    lines = ["=== INTRO ===", *quiz["intro"], ""]
    for item in quiz["questions"]:
        lines += [
            f"=== QUESTION {item['number']} ===",
            f"Question: {item['question']}",
            f"(Wait {item['countdown_seconds']} seconds)",
            f"Answer: {item['answer']}",
            ""
        ]
    lines += ["=== ENDING ===", quiz["ending"], ""]
    return "\n".join(lines)
