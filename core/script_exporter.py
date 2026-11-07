import json
from pathlib import Path

from config import OUTPUT_DIR
from core.quiz_generator import format_text_script


def part_directory(part_number):
    return OUTPUT_DIR / f"part_{part_number:03d}"


def export_quiz(quiz):
    part_dir = part_directory(quiz["part"])
    part_dir.mkdir(parents=True, exist_ok=True)
    (part_dir / "narration").mkdir(exist_ok=True)
    (part_dir / "subtitles").mkdir(exist_ok=True)
    (part_dir / "video").mkdir(exist_ok=True)
    (part_dir / "thumbnail").mkdir(exist_ok=True)

    text_path = part_dir / "script.txt"
    json_path = part_dir / "script.json"
    text_path.write_text(format_text_script(quiz), encoding="utf-8")
    json_path.write_text(json.dumps(quiz, indent=2, ensure_ascii=False), encoding="utf-8")
    return text_path, json_path, part_dir


def export_srt(quiz, part_directory_path, audio_durations=None):
    audio_durations = audio_durations or {}
    padding = 0.5
    cues = []
    cursor = 0.0

    if "intro" in audio_durations:
        intro_duration = max(8.0, audio_durations["intro"] + padding)
    else:
        intro_duration = 8.0
    cues.append((cursor, cursor + intro_duration, "\n".join(quiz["intro"])))
    cursor += intro_duration + 0.5

    for item in quiz["questions"]:
        number = item["number"]
        q_key = f"q{number}"
        a_key = f"a{number}"
        if q_key in audio_durations:
            question_duration = max(3.5, audio_durations[q_key] + padding)
        else:
            question_duration = 3.5
        cues.append((cursor, cursor + question_duration, item["question"]))
        cursor += question_duration + quiz.get("countdown_seconds", 5)

        if a_key in audio_durations:
            answer_duration = max(3.0, audio_durations[a_key] + padding)
        else:
            answer_duration = max(3.0, float(quiz.get("countdown_seconds", 0) and 3.0))
        cues.append((cursor, cursor + answer_duration, f"CORRECT ANSWER\n{item['answer']}"))
        cursor += answer_duration + 0.5

    if "ending" in audio_durations:
        ending_duration = max(6.0, audio_durations["ending"] + padding)
    else:
        ending_duration = 6.0
    cues.append((cursor, cursor + ending_duration, quiz["ending"]))

    path = Path(part_directory_path) / "subtitles" / f"part_{quiz['part']:03d}.srt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_format_srt(cues), encoding="utf-8")
    return path


def _format_srt(cues):
    blocks = []
    for index, (start, end, text) in enumerate(cues, 1):
        blocks.append(f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n")
    return "\n".join(blocks).strip() + "\n"


def _timestamp(seconds):
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds_value, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d},{millis:03d}"