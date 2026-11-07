import argparse
import json
import logging
from pathlib import Path

from config import (
    QUESTIONS_PER_PART,
    OUTPUT_DIR,
    KOKORO_RESPONSE_FORMAT,
    AUDIO_PADDING_SECONDS,
)
from core.question_manager import select_questions
from core.quiz_generator import build_quiz, format_text_script
from core.script_exporter import export_quiz, export_srt
from core.history_manager import load_history, next_part_number, record_question_usage, reset_history
from integrations.kokoro_tts import KokoroTTS, audio_duration as measure_audio
from integrations.hyperframes import create_composition, render_video

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate World General Knowledge Quiz scripts and videos.")
    parser.add_argument("--part", type=int, default=None, help="Part number. Defaults to the next sequential Part.")
    parser.add_argument("--start-part", type=int, default=None, help="First Part number for batch generation.")
    parser.add_argument("--total-parts", type=int, default=None, help="Number of Parts to generate in batch mode.")
    parser.add_argument("--count", type=int, default=QUESTIONS_PER_PART, help="Number of questions (default: 15).")
    parser.add_argument("--category", default="all", help="Category filter or 'all'.")
    parser.add_argument("--difficulty", default="all", choices=["all", "easy", "medium", "hard"])
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed for reproducible selection.")
    parser.add_argument("--tts", action="store_true", help="Generate narration using a running KokoroTTS server.")
    parser.add_argument("--render", action="store_true", help="Create HyperFrames composition and render MP4.")
    parser.add_argument("--reset-history", action="store_true", help="Clear used-question history and reset Part numbering.")
    return parser.parse_args()


def resolve_parts(args):
    if args.part is not None:
        if args.part < 1:
            raise SystemExit("--part must be 1 or greater.")
        return [args.part]

    total_parts = 1 if args.total_parts is None else args.total_parts
    if total_parts < 1:
        raise SystemExit("--total-parts must be 1 or greater.")

    if args.start_part is not None and args.start_part != 0:
        start = args.start_part
    else:
        start = next_part_number()
    if start < 1:
        raise SystemExit("--start-part must be 1 or greater.")
    return list(range(start, start + total_parts))


def part_audio_extension():
    return KOKORO_RESPONSE_FORMAT.strip(".")


def discover_cached_audio(part, part_dir):
    audio_map = {}
    audio_durations = {}
    narration_dir = part_dir / "narration"
    if not narration_dir.is_dir():
        return audio_map, audio_durations
    ext = part_audio_extension()
    candidates = {"intro": f"part_{part:03d}_intro.{ext}"}
    # question/answer files are added after the question count is known; discover generically.
    for path in sorted(narration_dir.glob(f"part_{part:03d}_*.{ext}")):
        stem = path.stem
        suffix = stem[len(f"part_{part:03d}_"):]
        if suffix == "intro":
            audio_map["intro"] = path
        elif suffix == "ending":
            audio_map["ending"] = path
        elif "_" not in suffix and suffix.startswith("q"):
            audio_map[suffix] = path
        elif suffix.startswith("a"):
            audio_map[suffix] = path
    for key, path in audio_map.items():
        try:
            audio_durations[key] = measure_audio(path)
        except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError):
            pass
    return audio_map, audio_durations


def generate_part(part, args, history=None):
    part_dir = OUTPUT_DIR / f"part_{part:03d}"
    if history is None:
        history = load_history()
    selected, pool_reset, history = select_questions(args.count, args.category, args.difficulty, args.seed, history=history)
    quiz = build_quiz(part, selected)
    text_path, json_path, resolved_part_dir = export_quiz(quiz)
    part_dir = resolved_part_dir

    audio_map, audio_durations = discover_cached_audio(part, part_dir)

    if args.tts:
        tts = KokoroTTS()
        narration_dir = part_dir / "narration"
        narration_dir.mkdir(parents=True, exist_ok=True)
        ext = part_audio_extension()
        try:
            intro_text = " ".join(quiz["intro"])
            audio_map["intro"] = tts.synthesize(intro_text, narration_dir / f"part_{part:03d}_intro.{ext}")
            for item in quiz["questions"]:
                n = item["number"]
                audio_map[f"q{n}"] = tts.synthesize(item["question"], narration_dir / f"part_{part:03d}_q{n:02d}.{ext}")
                audio_map[f"a{n}"] = tts.synthesize(f"The correct answer is {item['answer']}.", narration_dir / f"part_{part:03d}_a{n:02d}.{ext}")
            audio_map["ending"] = tts.synthesize(quiz["ending"], narration_dir / f"part_{part:03d}_ending.{ext}")
        except RuntimeError as exc:
            raise SystemExit(f"TTS failed for Part {part}: {exc}")
        audio_durations = {}
        for key, path in audio_map.items():
            try:
                audio_durations[key] = measure_audio(path)
            except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError) as exc:
                logger.warning("Could not measure audio duration for %s: %s", path, exc)
        print(f"\nGenerated {len(audio_map)} narration audio files for Part {part}.")
    else:
        # Use any cached audio already present so compositions and subtitles stay synchronized.
        pass

    srt_path = export_srt(quiz, part_dir, audio_durations if audio_durations else None)

    print(format_text_script(quiz))
    print(f"\nSaved text script: {text_path}")
    print(f"Saved JSON script: {json_path}")
    print(f"Saved subtitles: {srt_path}")
    if pool_reset:
        print("\nNOTE: The unused question pool was too small for this selection. History was cycled for this filtered pool.")

    if args.render:
        project_dir, duration, timeline = create_composition(quiz, audio_map)
        print(f"\nHyperFrames project: {project_dir}")
        print(f"Estimated composition duration: {duration:.1f} seconds")
        video_path = render_video(project_dir, part)
        print(f"Rendered video: {video_path}")

    question_ids = [question["id"] for question in selected]
    history = record_question_usage(history, question_ids, part)
    print(f"Marked {len(question_ids)} question IDs as used for Part {part}.")

    return part_dir, history


def main():
    args = parse_args()

    if args.reset_history:
        reset_history()
        print("Question history reset.")
        if args.part is None and args.start_part is None and args.total_parts is None and not args.tts and not args.render:
            return

    if args.count < 1:
        raise SystemExit("--count must be at least 1.")

    parts = resolve_parts(args)
    history = load_history()
    for part in parts:
        print(f"\n===== Generating Part {part} =====")
        _, history = generate_part(part, args, history)


if __name__ == "__main__":
    main()