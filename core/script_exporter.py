import json
from pathlib import Path

from config import OUTPUT_DIR
from core.quiz_generator import (
    ANSWER_MIN_SECONDS,
    DEFAULT_ENDING_SECONDS,
    DEFAULT_INTRO_SECONDS,
    ENDING_LINE_MIN_SECONDS,
    INTRO_LINE_MIN_SECONDS,
    QUESTION_MIN_SECONDS,
    format_text_script,
    line_duration,
    plan_line_durations,
)


def part_directory(part_number):
    return OUTPUT_DIR / f"part_{part_number:03d}"


def export_quiz(quiz, output_dir=None):
    if output_dir is None:
        part_dir = part_directory(quiz["part"])
    else:
        part_dir = Path(output_dir)
        part_dir.mkdir(parents=True, exist_ok=True)
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

    legacy_intro = line_duration(audio_durations.get("intro"), DEFAULT_INTRO_SECONDS)
    intro_durations = plan_line_durations(
        quiz["intro"], audio_durations, "intro", INTRO_LINE_MIN_SECONDS, legacy_intro
    )
    for line, duration in zip(quiz["intro"], intro_durations):
        cues.append((cursor, cursor + duration, line))
        cursor += duration
    cursor += padding

    for item in quiz["questions"]:
        number = item["number"]
        q_key = f"q{number}"
        a_key = f"a{number}"
        question_duration = line_duration(audio_durations.get(q_key), QUESTION_MIN_SECONDS)
        cues.append((cursor, cursor + question_duration, item["spoken"]))
        cursor += question_duration + quiz.get("countdown_seconds", 5)

        answer_duration = line_duration(audio_durations.get(a_key), ANSWER_MIN_SECONDS)
        cues.append((cursor, cursor + answer_duration, item["spoken_answer"]))
        cursor += answer_duration + padding

    ending_lines = quiz.get("ending_lines") or [quiz["ending"]]
    legacy_ending = line_duration(audio_durations.get("ending"), DEFAULT_ENDING_SECONDS)
    ending_durations = plan_line_durations(
        ending_lines, audio_durations, "ending", ENDING_LINE_MIN_SECONDS, legacy_ending
    )
    for line, duration in zip(ending_lines, ending_durations):
        cues.append((cursor, cursor + duration, line))
        cursor += duration

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