import argparse
import json
import logging
from pathlib import Path

from config import (
    FACEBOOK_REEL_QUESTION_COUNT,
    FACEBOOK_TEN_VIDEO_QUESTION_COUNT,
    QUESTIONS_PER_PART,
    OUTPUT_DIR,
    KOKORO_RESPONSE_FORMAT,
    AUDIO_PADDING_SECONDS,
    TTS_SPEED,
    TTS_SPEED_REEL,
)
from core.question_manager import load_questions, select_questions
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
    parser.add_argument("--publish-dry-run", action="store_true", help="Validate a generated Part and prepare a Facebook publication dry-run report.")
    parser.add_argument("--publish", action="store_true", help="Run the guarded Facebook publisher after preflight and local validation.")
    parser.add_argument("--publish-content-type", choices=["reel", "full_video", "ten_question_video"], default="reel", help="Facebook content type for --publish or --publish-dry-run.")
    parser.add_argument("--render-reels", action="store_true", help="Render a separate 3-to-5 question Facebook Reel from the same Part.")
    parser.add_argument("--render-facebook-reels", action="store_true", help="Alias for --render-reels.")
    parser.add_argument("--facebook-reels", action="store_true", help="Alias for --render-reels.")
    parser.add_argument("--reels-question-count", type=int, default=FACEBOOK_REEL_QUESTION_COUNT, help="Reel question count, 3-5.")
    parser.add_argument("--facebook-reels-question-count", type=int, default=None, help="Alias for the Reel question count.")
    parser.add_argument("--render-ten-video", action="store_true", help="Render a separate 10-question Facebook Page Video.")
    parser.add_argument("--render-facebook-ten-video", action="store_true", help="Alias for --render-ten-video.")
    parser.add_argument("--facebook-ten-video", action="store_true", help="Alias for --render-ten-video.")
    parser.add_argument("--ten-question-count", type=int, default=FACEBOOK_TEN_VIDEO_QUESTION_COUNT, help="Requested Facebook 10-video question count.")
    parser.add_argument("--facebook-ten-question-count", type=int, default=None, help="Alias for the Facebook 10-video question count.")

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


def _synthesize_lines(tts, lines, narration_dir, part, prefix, ext):
    """Synthesize one clip per line so the spoken words match the on-screen text."""
    audio_map = {}
    for index, line in enumerate(lines, 1):
        key = f"{prefix}_{index}"
        audio_map[key] = tts.synthesize(line, narration_dir / f"part_{part:03d}_{key}.{ext}")
    return audio_map


def _copy_matching_line_audio(target, target_durations, source, source_durations, prefix, target_lines, source_lines):
    """Copy narration clips only when the spoken lines match the displayed lines."""
    if list(target_lines) != list(source_lines):
        return
    for index in range(len(target_lines)):
        key = f"{prefix}_{index + 1}"
        if key in target or key not in source:
            continue
        target[key] = source[key]
        if key in source_durations:
            target_durations[key] = source_durations[key]


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
        elif suffix == "reel_intro":
            audio_map["reel_intro"] = path
        elif suffix == "ending":
            audio_map["ending"] = path
        elif suffix.startswith("intro_") or suffix.startswith("ending_"):
            audio_map[suffix] = path
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
        tts = KokoroTTS(speed=TTS_SPEED)
        narration_dir = part_dir / "narration"
        narration_dir.mkdir(parents=True, exist_ok=True)
        ext = part_audio_extension()
        try:
            audio_map.update(_synthesize_lines(tts, quiz["intro"], narration_dir, part, "intro", ext))
            for item in quiz["questions"]:
                n = item["number"]
                audio_map[f"q{n}"] = tts.synthesize(item["spoken"], narration_dir / f"part_{part:03d}_q{n:02d}.{ext}")
                audio_map[f"a{n}"] = tts.synthesize(item["spoken_answer"], narration_dir / f"part_{part:03d}_a{n:02d}.{ext}")
            audio_map.update(_synthesize_lines(tts, quiz["ending_lines"], narration_dir, part, "ending", ext))
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
    print(f"Question bank: {len(load_questions()):,} questions available.")
    if pool_reset:
        print(
            "\nNOTE: The unused question pool was too small for this selection. "
            "The questions used longest ago were recycled for this Part."
        )

    render_reels = bool(
        getattr(args, "render_reels", False)
        or getattr(args, "render_facebook_reels", False)
        or getattr(args, "facebook_reels", False)
    )
    render_ten_video = bool(
        getattr(args, "render_ten_video", False)
        or getattr(args, "render_facebook_ten_video", False)
        or getattr(args, "facebook_ten_video", False)
    )
    if args.render or render_reels or render_ten_video:
        if args.render:
            project_dir, duration, timeline = create_composition(quiz, audio_map)
            print(f"\nHyperFrames project: {project_dir}")
            print(f"Estimated composition duration: {duration:.1f} seconds")
            video_path = render_video(project_dir, part)
            print(f"Rendered video: {video_path}")

        if render_reels:
            reel_question_count = getattr(args, "reels_question_count", None)
            if reel_question_count is None:
                reel_question_count = getattr(args, "facebook_reels_question_count", None)
            if reel_question_count is None:
                reel_question_count = FACEBOOK_REEL_QUESTION_COUNT
            if reel_question_count < 3 or reel_question_count > 5:
                raise SystemExit("Facebook Reels question count must be between 3 and 5.")
            if len(selected) < reel_question_count:
                raise SystemExit(f"Only {len(selected)} questions are available; cannot render {reel_question_count} Reel questions.")

            reels_dir = part_dir / "facebook" / "reels"
            reels_dir.mkdir(parents=True, exist_ok=True)
            reel_questions = selected[:reel_question_count]
            quiz_reel = build_quiz(part, reel_questions, content_type="reel")
            _, reel_json_path, _ = export_quiz(quiz_reel, output_dir=reels_dir)
            reel_keys = ["intro", "ending"] + [f"q{number}" for number in range(1, reel_question_count + 1)] + [f"a{number}" for number in range(1, reel_question_count + 1)]

            reel_audio_map = {}
            reel_audio_durations = {}
            if args.tts:
                reel_tts = KokoroTTS(speed=TTS_SPEED_REEL)
                ext = part_audio_extension()
                reel_narration_dir = reels_dir / "narration"
                reel_narration_dir.mkdir(parents=True, exist_ok=True)
                try:
                    # The Reel keeps one intro and one outro clip so its duration
                    # stays inside Meta's 90 second Reel limit.
                    reel_audio_map["intro"] = reel_tts.synthesize(" ".join(quiz_reel["intro"]), reel_narration_dir / f"part_{part:03d}_intro.{ext}")
                    for item in quiz_reel["questions"]:
                        number = item["number"]
                        reel_audio_map[f"q{number}"] = reel_tts.synthesize(item["spoken"], reel_narration_dir / f"part_{part:03d}_q{number:02d}.{ext}")
                        reel_audio_map[f"a{number}"] = reel_tts.synthesize(item["spoken_answer"], reel_narration_dir / f"part_{part:03d}_a{number:02d}.{ext}")
                    reel_audio_map["ending"] = reel_tts.synthesize(" ".join(quiz_reel["ending_lines"]), reel_narration_dir / f"part_{part:03d}_ending.{ext}")
                except RuntimeError as exc:
                    raise SystemExit(f"TTS failed for Part {part} Reel: {exc}")
                for key, path in reel_audio_map.items():
                    try:
                        reel_audio_durations[key] = measure_audio(path)
                    except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError):
                        pass
            else:
                cached_map, cached_durations = discover_cached_audio(part, reels_dir)
                if cached_map:
                    reel_audio_map.update(cached_map)
                    reel_audio_durations.update(cached_durations)

            # Full-part clips are valid for the shared question and answer
            # clips; only intro and ending differ between videos.
            for key in [f"q{number}" for number in range(1, reel_question_count + 1)] + [f"a{number}" for number in range(1, reel_question_count + 1)]:
                if key not in reel_audio_map and key in audio_map:
                    reel_audio_map[key] = audio_map[key]
                    if key not in reel_audio_durations and key in audio_durations:
                        reel_audio_durations[key] = audio_durations[key]
            _copy_matching_line_audio(
                reel_audio_map, reel_audio_durations, audio_map, audio_durations,
                "intro", quiz_reel["intro"], quiz["intro"],
            )
            _copy_matching_line_audio(
                reel_audio_map, reel_audio_durations, audio_map, audio_durations,
                "ending", quiz_reel["ending_lines"], quiz["ending_lines"],
            )
            reel_srt_path = export_srt(quiz_reel, reels_dir, {key: value for key, value in reel_audio_durations.items() if value is not None})
            if args.render or render_reels:
                reel_project_dir, reel_duration, reel_timeline = create_composition(quiz_reel, reel_audio_map, content_type="reel")
                print(f"Reel HyperFrames project: {reel_project_dir}")
                print(f"Reel composition duration: {reel_duration:.1f} seconds")
                reels_output_path = reels_dir / f"world_general_knowledge_quiz_part_{part:03d}_reel.mp4"
                reel_video_path = render_video(reel_project_dir, part, output_path=reels_output_path)
                print(f"Rendered Facebook Reel: {reel_video_path}")
                print(f"Reel SRT: {reel_srt_path}")

        if render_ten_video:
            ten_question_count = getattr(args, "facebook_ten_question_count", FACEBOOK_TEN_VIDEO_QUESTION_COUNT)
            if ten_question_count is None:
                ten_question_count = FACEBOOK_TEN_VIDEO_QUESTION_COUNT
            if ten_question_count != 10:
                raise SystemExit("Facebook 10-question video requires exactly 10 questions.")
            if len(selected) < ten_question_count:
                raise SystemExit(f"Only {len(selected)} questions are available; cannot render a 10-question video.")

            ten_dir = part_dir / "facebook" / "videos"
            ten_dir.mkdir(parents=True, exist_ok=True)
            ten_questions = selected[:ten_question_count]
            quiz_ten = build_quiz(part, ten_questions, content_type="ten_question_video")
            _, ten_json_path, _ = export_quiz(quiz_ten, output_dir=ten_dir)
            ten_keys = ["intro", "ending"] + [f"q{number}" for number in range(1, ten_question_count + 1)] + [f"a{number}" for number in range(1, ten_question_count + 1)]
            ten_audio_map = {}
            ten_audio_durations = {}
            if args.tts:
                ten_tts = KokoroTTS(speed=TTS_SPEED)
                ext = part_audio_extension()
                ten_narr_dir = ten_dir / "narration"
                ten_narr_dir.mkdir(parents=True, exist_ok=True)
                try:
                    ten_audio_map.update(_synthesize_lines(ten_tts, quiz_ten["intro"], ten_narr_dir, part, "intro", ext))
                    for item in quiz_ten["questions"]:
                        number = item["number"]
                        ten_audio_map[f"q{number}"] = ten_tts.synthesize(item["spoken"], ten_narr_dir / f"part_{part:03d}_q{number:02d}.{ext}")
                        ten_audio_map[f"a{number}"] = ten_tts.synthesize(item["spoken_answer"], ten_narr_dir / f"part_{part:03d}_a{number:02d}.{ext}")
                    ten_audio_map.update(_synthesize_lines(ten_tts, quiz_ten["ending_lines"], ten_narr_dir, part, "ending", ext))
                except RuntimeError as exc:
                    raise SystemExit(f"TTS failed for Part {part} 10-question video: {exc}")
                for key, path in ten_audio_map.items():
                    try:
                        ten_audio_durations[key] = measure_audio(path)
                    except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError):
                        pass
            else:
                cached_map, cached_durations = discover_cached_audio(part, ten_dir)
                if cached_map:
                    ten_audio_map.update(cached_map)
                    ten_audio_durations.update(cached_durations)

            for key in [f"q{number}" for number in range(1, ten_question_count + 1)] + [f"a{number}" for number in range(1, ten_question_count + 1)]:
                if key not in ten_audio_map and key in audio_map:
                    ten_audio_map[key] = audio_map[key]
                    if key not in ten_audio_durations and key in audio_durations:
                        ten_audio_durations[key] = audio_durations[key]
            _copy_matching_line_audio(
                ten_audio_map, ten_audio_durations, audio_map, audio_durations,
                "intro", quiz_ten["intro"], quiz["intro"],
            )
            _copy_matching_line_audio(
                ten_audio_map, ten_audio_durations, audio_map, audio_durations,
                "ending", quiz_ten["ending_lines"], quiz["ending_lines"],
            )
            ten_srt_path = export_srt(quiz_ten, ten_dir, {key: value for key, value in ten_audio_durations.items() if value is not None})
            if args.render or render_ten_video:
                ten_project_dir, _, _ = create_composition(quiz_ten, ten_audio_map, content_type="ten_question_video", tracker=True)
                print(f"10-question Facebook HyperFrames project: {ten_project_dir}")
                ten_output_path = ten_dir / f"world_general_knowledge_quiz_part_{part:03d}_10_questions.mp4"
                ten_video_path = render_video(ten_project_dir, part, output_path=ten_output_path)
                print(f"Rendered 10-question Facebook Page Video: {ten_video_path}")
                print(f"10-question subtitles: {ten_srt_path}")

    question_ids = [question["id"] for question in selected]
    history = record_question_usage(history, question_ids, part)
    print(f"Marked {len(question_ids)} question IDs as used for Part {part}.")
    return part_dir, history


def _run_publish_reel(args, dry_run: bool = True):
    from config import FACEBOOK_PUBLISH_DRY_RUN, FACEBOOK_PUBLISH_ENABLED
    from core.publish_manager import FacebookPublishManager
    from integrations.facebook_publisher import FacebookPublisher

    part_number = args.part if args.part is not None else 1
    content_type = getattr(args, "publish_content_type", "reel") or "reel"
    part_dir = OUTPUT_DIR / f"part_{part_number:03d}"
    if not part_dir.is_dir():
        raise SystemExit(f"Generated Part directory not found: {part_dir}")
    if content_type == "full_video":
        video_path = part_dir / "video" / f"world_general_knowledge_quiz_part_{part_number:03d}.mp4"
    elif content_type == "ten_question_video":
        video_path = part_dir / "facebook" / "videos" / f"world_general_knowledge_quiz_part_{part_number:03d}_10_questions.mp4"
    else:
        video_path = part_dir / "facebook" / "reels" / f"world_general_knowledge_quiz_part_{part_number:03d}_reel.mp4"
    if not video_path.is_file():
        raise SystemExit(f"Generated MP4 not found: {video_path}")

    quiz_path = part_dir / "script.json"
    if not quiz_path.is_file():
        raise SystemExit(f"Generated quiz JSON not found: {quiz_path}")
    quiz = json.loads(quiz_path.read_text(encoding="utf-8"))

    if content_type == "reel":
        suffix = " Reel"
    elif content_type == "ten_question_video":
        suffix = " | 10 Questions"
    else:
        suffix = " Video"
    title = f"{quiz.get('title', 'World General Knowledge Quiz')} - Part {part_number}{suffix}"
    if content_type == "ten_question_video":
        description = (
            "🌍 Think you know the world? Test yourself with 10 quick general knowledge questions!\n\n"
            "Comment your score out of 10 👇 and challenge a friend to beat it.\n\n"
            "#WorldGeneralKnowledgeQuiz #GeneralKnowledge #Trivia #QuizTime #LearnOnFacebook"
        )
    else:
        description = (
            f"{quiz.get('ending', 'World General Knowledge Quiz')}\n\n"
            f"Question set: {quiz.get('part', part_number)}. "
            "Answer in the comments and challenge your friends."
        )

    manager = FacebookPublishManager()
    publisher = FacebookPublisher(dry_run=dry_run)
    requested_live = not dry_run
    if requested_live and (not FACEBOOK_PUBLISH_ENABLED or FACEBOOK_PUBLISH_DRY_RUN):
        raise SystemExit(
            "Live Facebook publishing is disabled. Set FACEBOOK_PUBLISH_ENABLED=true and "
            "FACEBOOK_PUBLISH_DRY_RUN=false only after completing dry-run and manual tests."
        )

    try:
        if dry_run or FACEBOOK_PUBLISH_DRY_RUN or not FACEBOOK_PUBLISH_ENABLED:
            report = publisher.run_dry_run(part_number, video_path, title, description, manager, content_type=content_type)
            print("\nFacebook publication dry-run report")
            print(f"Content type: {content_type}")
            print(f"Part: {report.part_number}")
            print(f"Video: {report.video_path}")
            print(f"Content hash: {report.content_hash}")
            print("Preflight: " + ("PASS" if report.preflight["success"] else "FAIL"))
            for error in report.preflight["errors"]:
                print(f"  - {error}")
            print(f"Status: {report.publication_status}")
            print(f"Report: {report.report_path}")
            print("No real Meta Graph API upload or publish request was performed.")
            return

        if content_type == "full_video":
            result = publisher.publish_full_video(part_number, video_path, title, description, manager)
        elif content_type == "ten_question_video":
            result = publisher.publish_ten_question_video(part_number, video_path, title, description, manager)
        else:
            result = publisher.publish_reel(part_number, video_path, title, description, manager)
    except Exception as exc:
        print(f"Facebook publishing failed for Part {part_number}: {exc}")
        raise SystemExit(1) from exc

    print("\nFacebook publication completed" if result.get("success") else "\nFacebook publication was not successful")
    if result.get("skipped"):
        print(f"Skipped reason: {result.get('reason')}")
    print(f"Part: {result.get('part_number', part_number)}")
    print(f"Video ID: {result.get('meta_video_id')}")
    print(f"Post ID: {result.get('meta_post_id')}")
    if result.get("errors"):
        print("Errors:")
        for error in result["errors"]:
            print(f"  - {error}")
    if not result.get("success"):
        raise SystemExit(1)


def main():
    args = parse_args()

    if args.publish_dry_run or args.publish:
        _run_publish_reel(args, dry_run=args.publish_dry_run)
        return


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
