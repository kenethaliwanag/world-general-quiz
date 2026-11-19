"""Create a vertical HyperFrames HTML composition and optionally render it."""
import json
import os
import shutil
import subprocess
from pathlib import Path

from config import (
    PROJECT_ROOT,
    OUTPUT_DIR,
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_FPS,
    COUNTDOWN_SECONDS,
    ANSWER_DISPLAY_SECONDS,
    TRANSITION_SECONDS,
    AUDIO_PADDING_SECONDS,
    AUDIO_DIR,
    VIDEOS_DIR,
    SFX_TICK_PATH,
    SFX_TIMEUP_PATH,
    SFX_TICK_VOLUME,
    SFX_TIMEUP_VOLUME,
    WATERMARK_IMAGE_PATH,
)
from integrations.kokoro_tts import audio_duration as measure_audio_duration
from core.quiz_generator import (
    DEFAULT_ENDING_SECONDS,
    DEFAULT_INTRO_SECONDS,
    ENDING_LINE_MIN_SECONDS,
    INTRO_LINE_MIN_SECONDS,
    line_duration,
    plan_line_durations,
)

# Ten-question quiz screen layout (1080x1920).  Mirrors the reference board:
# branded header, question block, countdown bar and a two-column answer grid.
CONTENT_LEFT_PX = 54
CONTENT_WIDTH_PX = 972
TIMER_WIDTH_PX = 860
SLOT_COLUMNS = ((54, 122, 391), (567, 635, 391))
SLOT_GRID_TOP_PX = 800
SLOT_GRID_BOTTOM_PX = 1700
SLOT_BOX_HEIGHT_PX = 155
SLOT_NUMBER_WIDTH_PX = 60

DIFFICULTY_COLORS = {"easy": "#4ade80", "medium": "#fbbf24", "hard": "#f87171"}
DIFFICULTY_TEXT = {"easy": "#0d2a1c", "medium": "#3a2a00", "hard": "#3a0d0d"}


def _esc(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def _audio_duration(path, fallback=None):
    try:
        return measure_audio_duration(path)
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return fallback


def _answer_font_size(answer: str) -> int:
    length = len(answer)
    if length <= 12:
        return 32
    if length <= 22:
        return 28
    return 24


def _question_font_size(question: str) -> int:
    length = len(question)
    if length <= 45:
        return 52
    if length <= 70:
        return 46
    return 42


def _timer_color(fraction: float) -> str:
    if fraction > 0.6:
        return "#4ade80"
    if fraction > 0.3:
        return "#fbbf24"
    return "#ef4444"


def _title_lines(title: str) -> list[str]:
    words = str(title).upper().split()
    if len(words) < 4:
        return [" ".join(words)]
    half = (len(words) + 1) // 2
    return [" ".join(words[:half]), " ".join(words[half:])]


def create_composition(quiz, audio_map=None, content_type="full", tracker=None, output_root=None):
    audio_map = audio_map or {}
    if tracker is None:
        tracker = content_type.startswith("ten_question")
    part = quiz["part"]
    if content_type == "reel":
        project_subdir = "reels"
    elif content_type.startswith("ten_question"):
        project_subdir = "videos"
    else:
        project_subdir = ""
    project_components = [Path(output_root) if output_root is not None else OUTPUT_DIR, "hyperframes", f"part_{part:03d}"]
    if project_subdir:
        project_components.append(project_subdir)
    project_dir = Path(*project_components)
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Copy generated audio into the HyperFrames project so media paths are portable.
    copied_audio = {}
    for key, source in audio_map.items():
        src = Path(source)
        if src.exists():
            target = assets_dir / src.name
            shutil.copy2(src, target)
            copied_audio[key] = f"assets/{target.name}"

    audio_durations = {}
    for key, source in audio_map.items():
        src = Path(source)
        target = assets_dir / src.name if src.exists() else None
        if target is not None and target.exists():
            duration = _audio_duration(target)
            if duration is not None:
                audio_durations[key] = duration

    copied_sfx = {}
    sfx_durations = {}

    copied_watermark = ""
    watermark_source = Path(WATERMARK_IMAGE_PATH)
    if watermark_source.is_file():
        target = assets_dir / watermark_source.name
        if not target.exists() or watermark_source.stat().st_size != target.stat().st_size:
            shutil.copy2(watermark_source, target)
        copied_watermark = f"assets/{target.name}"
    for sfx_key, source_path in (("tick", SFX_TICK_PATH), ("timeup", SFX_TIMEUP_PATH)):
        source = Path(source_path)
        if source.is_file():
            target = assets_dir / source.name
            if not target.exists() or source.stat().st_size != target.stat().st_size:
                shutil.copy2(source, target)
            copied_sfx[sfx_key] = f"assets/{target.name}"
            sfx_durations[sfx_key] = _audio_duration(target, 0.1 if sfx_key == "tick" else 0.22) or (
                0.1 if sfx_key == "tick" else 0.22
            )

    cursor = 0.0
    elements = []
    track = 0

    def add_text(text, start, duration, class_name, element_id, extra=""):
        nonlocal track
        elements.append(
            f'<div id="{_esc(element_id)}" class="clip {class_name}" data-start="{start:.3f}" '
            f'data-duration="{duration:.3f}" data-track-index="{track}" {extra}>{_esc(text)}</div>'
        )
        track += 1

    def add_audio(key, start, duration):
        nonlocal track
        src = copied_audio.get(key)
        if src:
            elements.append(
                f'<audio id="audio-{_esc(key)}" data-start="{start:.3f}" data-duration="{duration:.3f}" '
                f'data-track-index="{track}" data-volume="1" src="{_esc(src)}"></audio>'
            )
            track += 1

    def add_sfx(media_key, source_key, start, volume=1.0):
        nonlocal track
        src = copied_sfx.get(source_key)
        if src:
            duration = sfx_durations.get(source_key, 0.1)
            elements.append(
                f'<audio id="sfx-{_esc(media_key)}" data-start="{start:.3f}" data-duration="{duration:.3f}" '
                f'data-track-index="{track}" data-volume="{volume:.2f}" src="{_esc(src)}"></audio>'
            )
            track += 1

    part_id = f"world-quiz-part-{part}"
    intro_lines = quiz["intro"]

    # Reveal each intro phrase during the portion of the narration that
    # actually speaks it.  Avoid fixed starts so the text and audio stay
    # synchronized.
    def word_progress_cues(text, start, total_duration):
        words = text.split()
        if not words:
            return []
        weights = [max(len(word), 1) for word in words]
        total_weight = sum(weights)
        section_end = start + total_duration
        offsets = [0.0]
        for weight in weights:
            offsets.append(offsets[-1] + weight / total_weight * total_duration)
        cues = []
        prefix = []
        for index, word in enumerate(words):
            prefix.append(word)
            word_start = start + offsets[index]
            word_end = start + offsets[index + 1]
            if index + 1 == len(words):
                word_end = section_end
            cues.append((word_start, " ".join(prefix), max(0.01, word_end - word_start)))
        return cues

    intro_word_counts = [len(line.split()) for line in intro_lines]
    intro_total_words = sum(intro_word_counts) or 1
    intro_cursor = cursor
    intro_styles = [
        ("title", "intro-title"),
        ("subtitle", "intro-subtitle"),
        ("partline", "intro-partline"),
        ("hook", "intro-hook"),
    ]
    legacy_intro_duration = line_duration(audio_durations.get("intro"), DEFAULT_INTRO_SECONDS)
    intro_line_durations = plan_line_durations(
        intro_lines, audio_durations, "intro", INTRO_LINE_MIN_SECONDS, legacy_intro_duration
    )
    has_intro_line_clips = any(f"intro_{index + 1}" in copied_audio for index in range(len(intro_lines)))
    for class_index, (line, seconds) in enumerate(zip(intro_lines, intro_line_durations)):
        css_class, element_prefix = intro_styles[min(class_index, len(intro_styles) - 1)]
        for index, (cue_start, text, duration) in enumerate(word_progress_cues(line, intro_cursor, seconds)):
            add_text(text, cue_start, duration, css_class, f"{element_prefix}-word-{index + 1}")
        line_key = f"intro_{class_index + 1}"
        if has_intro_line_clips and copied_audio.get(line_key):
            add_audio(line_key, intro_cursor, audio_durations.get(line_key) or seconds)
        intro_cursor += seconds
    intro_duration = intro_cursor - cursor
    if not has_intro_line_clips and copied_audio.get("intro"):
        add_audio("intro", cursor, audio_durations.get("intro") or intro_duration)
    cursor += intro_duration + TRANSITION_SECONDS
    quiz_start_cursor = cursor

    tracker_events = []
    for item in quiz["questions"]:
        n = item["number"]
        question_text = item["question"]
        question_start = cursor
        q_key, a_key = f"q{n}", f"a{n}"
        question_audio_duration = audio_durations.get(q_key)
        if question_audio_duration is not None:
            question_duration = max(3.5, question_audio_duration + AUDIO_PADDING_SECONDS)
        else:
            question_duration = 3.5
        answer_audio_duration = audio_durations.get(a_key)
        if answer_audio_duration is not None:
            reveal_duration = max(ANSWER_DISPLAY_SECONDS, answer_audio_duration + AUDIO_PADDING_SECONDS)
        else:
            reveal_duration = ANSWER_DISPLAY_SECONDS
        if tracker:
            # The question stays up through its countdown, its answer reveal and
            # the transition, so it is replaced only when the next one starts.
            question_visible_duration = (
                question_duration + COUNTDOWN_SECONDS + reveal_duration + TRANSITION_SECONDS
            )
        else:
            question_visible_duration = question_duration + COUNTDOWN_SECONDS
        if tracker:
            add_text(f"QUESTION {n}", cursor, question_visible_duration, "qlabel", f"q{n}-label")
            difficulty = str(item.get("difficulty", "easy")).lower()
            add_text(
                difficulty.upper(),
                cursor,
                question_visible_duration,
                "qdiff",
                f"q{n}-difficulty",
                extra=(
                    f'style="background:{DIFFICULTY_COLORS.get(difficulty, DIFFICULTY_COLORS["easy"])};'
                    f'color:{DIFFICULTY_TEXT.get(difficulty, DIFFICULTY_TEXT["easy"])}"'
                ),
            )
        else:
            add_text(f"QUESTION {n:02d}", cursor, question_visible_duration, "eyebrow", f"q{n}-eyebrow")
        add_text(
            question_text,
            cursor,
            question_visible_duration,
            "question",
            f"q{n}-question",
            extra=f'style="font-size:{_question_font_size(question_text)}px"' if tracker else "",
        )
        if copied_audio.get(q_key):
            add_audio(q_key, cursor, question_audio_duration if question_audio_duration is not None else question_duration)
        countdown_start = cursor + question_duration
        for second in range(COUNTDOWN_SECONDS, 0, -1):
            tick_start = countdown_start + (COUNTDOWN_SECONDS - second)
            add_text(str(second), tick_start, 1.0, "countdown", f"q{n}-countdown-{second}")
            add_sfx(f"q{n}-{second}-tick", "tick", tick_start, SFX_TICK_VOLUME)
            if tracker:
                fraction = second / COUNTDOWN_SECONDS
                add_text(
                    "",
                    tick_start,
                    1.0,
                    "timer-fill",
                    f"q{n}-timer-{second}",
                    extra=f'style="width:{fraction * TIMER_WIDTH_PX:.0f}px;background:{_timer_color(fraction)}"',
                )
        if tracker:
            add_text("", countdown_start, float(COUNTDOWN_SECONDS), "timer-track", f"q{n}-timer-track")
        timeup_start = countdown_start + COUNTDOWN_SECONDS
        add_sfx(f"q{n}-timeup", "timeup", timeup_start, SFX_TIMEUP_VOLUME)
        cursor = countdown_start + COUNTDOWN_SECONDS

        answer_reveal_start = cursor
        if tracker:
            tracker_events.append((n, question_text, item["answer"], question_start, answer_reveal_start))
        else:
            add_text("CORRECT ANSWER", cursor, reveal_duration, "eyebrow answer-label", f"q{n}-answer-label")
            add_text(item["answer"], cursor, reveal_duration, "answer", f"q{n}-answer")
        if copied_audio.get(a_key):
            add_audio(a_key, cursor, answer_audio_duration if answer_audio_duration is not None else reveal_duration)
        cursor += reveal_duration + TRANSITION_SECONDS

    quiz_end_cursor = cursor
    ending_lines = quiz.get("ending_lines") or [quiz["ending"]]
    ending_styles = [
        ("eyebrow", "ending-eyebrow"),
        ("ending", "ending-text"),
        ("cta", "ending-cta"),
        ("cta-sub", "ending-cta-sub"),
    ]
    legacy_ending_duration = line_duration(audio_durations.get("ending"), DEFAULT_ENDING_SECONDS)
    ending_line_durations = plan_line_durations(
        ending_lines, audio_durations, "ending", ENDING_LINE_MIN_SECONDS, legacy_ending_duration
    )
    has_ending_line_clips = any(f"ending_{index + 1}" in copied_audio for index in range(len(ending_lines)))
    ending_cursor = cursor
    for class_index, (line, seconds) in enumerate(zip(ending_lines, ending_line_durations)):
        css_class, element_prefix = ending_styles[min(class_index, len(ending_styles) - 1)]
        if css_class in ("cta", "cta-sub"):
            add_text(line, ending_cursor, seconds, css_class, element_prefix)
        else:
            for index, (cue_start, text, duration) in enumerate(word_progress_cues(line, ending_cursor, seconds)):
                add_text(text, cue_start, duration, css_class, f"{element_prefix}-word-{index + 1}")
        line_key = f"ending_{class_index + 1}"
        if has_ending_line_clips and copied_audio.get(line_key):
            add_audio(line_key, ending_cursor, audio_durations.get(line_key) or seconds)
        ending_cursor += seconds
    ending_duration = ending_cursor - cursor
    add_text(f"PART {part}", ending_cursor - 2.5, 2.5, "partline ending-partline", "ending-part")
    if not has_ending_line_clips and copied_audio.get("ending"):
        add_audio("ending", cursor, audio_durations.get("ending") or ending_duration)
    cursor = ending_cursor

    if tracker:
        tracker_end = quiz_end_cursor
        header_duration = max(0.01, tracker_end - quiz_start_cursor)
        for index, line in enumerate(_title_lines(quiz.get("title", "World General Knowledge Quiz"))):
            add_text(
                line,
                quiz_start_cursor,
                header_duration,
                "quiz-title",
                f"quiz-title-{index + 1}",
                extra=f'style="top:{168 + index * 66}px"',
            )
        add_text(f"PART {part}", quiz_start_cursor, header_duration, "part-badge", "quiz-part-badge")
        slot_rows = max(1, (len(tracker_events) + 1) // 2)
        pitch = (SLOT_GRID_BOTTOM_PX - SLOT_GRID_TOP_PX) / slot_rows
        for number, _question, answer, question_start, answer_reveal_start in tracker_events:
            row = (number - 1) % slot_rows
            column = (number - 1) // slot_rows
            number_left, box_left, box_width = SLOT_COLUMNS[min(column, len(SLOT_COLUMNS) - 1)]
            top_px = SLOT_GRID_TOP_PX + row * pitch
            box_height = min(SLOT_BOX_HEIGHT_PX, pitch - 20)
            number_extra = (
                f'style="left:{number_left}px;width:{SLOT_NUMBER_WIDTH_PX}px;'
                f'top:{top_px:.0f}px;height:{box_height:.0f}px"'
            )
            box_style = (
                f"left:{box_left}px;width:{box_width}px;"
                f"top:{top_px:.0f}px;height:{box_height:.0f}px"
            )
            add_text(f"{number})", quiz_start_cursor, header_duration, "slot-num", f"slot-num-{number}", extra=number_extra)
            add_text(f"{number})", question_start, max(0.01, answer_reveal_start - question_start), "slot-num-active", f"slot-num-active-{number}", extra=number_extra)
            add_text("", quiz_start_cursor, max(0.01, question_start - quiz_start_cursor), "slot-box slot-box-pending", f"slot-box-pending-{number}", extra=f'style="{box_style}"')
            add_text("", question_start, max(0.01, answer_reveal_start - question_start), "slot-box slot-box-active", f"slot-box-active-{number}", extra=f'style="{box_style}"')
            add_text(answer, answer_reveal_start, max(0.01, tracker_end - answer_reveal_start), "slot-box slot-box-done", f"slot-box-done-{number}", extra=f'style="{box_style};font-size:{_answer_font_size(answer)}px"')

    if copied_watermark:
        elements.append(
            f'<img id="top-watermark" class="clip watermark" data-start="0.000" '
            f'data-duration="{cursor:.3f}" data-track-index="{track}" src="{_esc(copied_watermark)}" alt="World General Knowledge Quiz watermark">'
        )
        track += 1

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={VIDEO_WIDTH}, height={VIDEO_HEIGHT}">
<title>World General Knowledge Quiz - Part {part}</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
*{{box-sizing:border-box}} html,body{{margin:0;width:100%;height:100%;background:#071426;color:#fff;font-family:Arial,Helvetica,sans-serif}}
#root{{position:relative;width:{VIDEO_WIDTH}px;height:{VIDEO_HEIGHT}px;overflow:hidden;background:
radial-gradient(circle at 50% 35%,rgba(25,92,140,.45),transparent 42%),
linear-gradient(145deg,#071426 0%,#102b46 55%,#06101d 100%)}}
#root:before{{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.16) 1px,transparent 1px);background-size:42px 42px;opacity:.25}}
#root:after{{content:"";position:absolute;inset:26px;border:2px solid rgba(230,190,90,.35);border-radius:34px;pointer-events:none}}
.clip{{position:absolute;z-index:2;left:8%;width:84%;text-align:center;display:flex;align-items:center;justify-content:center;padding:20px;opacity:1}}
.title{{top:25%;height:18%;font-size:88px;line-height:1.08;font-weight:900;color:#f5cf72;text-shadow:0 5px 22px #000}}
.subtitle{{top:44%;height:13%;font-size:48px;line-height:1.25;font-weight:700}}
.partline{{top:61%;height:10%;font-size:38px;letter-spacing:5px;color:#f5cf72;font-weight:800}}
.eyebrow{{top:18%;height:7%;font-size:34px;letter-spacing:8px;color:#f5cf72;font-weight:800}}
.question{{top:30%;height:33%;font-size:65px;line-height:1.18;font-weight:800;text-shadow:0 4px 20px #000}}
.countdown{{top:67%;height:16%;font-size:150px;font-weight:900;color:#f5cf72;text-shadow:0 0 35px rgba(245,207,114,.5)}}
.answer-label{{color:#77e0a3}}
.answer{{top:34%;height:32%;font-size:76px;line-height:1.15;font-weight:900;color:#77e0a3;text-shadow:0 0 30px rgba(70,220,145,.35)}}
.ending{{top:34%;height:30%;font-size:66px;line-height:1.2;font-weight:900}}
.tracker-layout .question{{top:466px;left:{CONTENT_LEFT_PX}px;width:{CONTENT_WIDTH_PX}px;height:240px;font-size:52px;line-height:1.2;text-align:left;justify-content:flex-start;padding:0}}
.tracker-layout .countdown{{top:700px;left:930px;width:96px;height:62px;font-size:44px;line-height:1;justify-content:flex-end;text-align:right;padding:0;text-shadow:0 0 24px rgba(245,207,114,.55)}}
.tracker-layout .watermark{{top:30px;width:120px}}
.tracker-layout .eyebrow{{top:640px;height:90px;font-size:44px;letter-spacing:6px}}
.tracker-layout .ending{{top:760px;left:{CONTENT_LEFT_PX}px;width:{CONTENT_WIDTH_PX}px;height:460px;font-size:92px;line-height:1.22}}
.tracker-layout .cta{{top:1330px;width:940px;height:110px;font-size:42px}}
.tracker-layout .cta-sub{{top:1460px;height:60px;font-size:30px}}
.tracker-layout .ending-partline{{top:1580px;height:70px;font-size:34px;letter-spacing:6px}}
.quiz-title{{position:absolute;z-index:4;left:{CONTENT_LEFT_PX}px;width:{CONTENT_WIDTH_PX}px;height:66px;font-size:54px;font-weight:900;letter-spacing:1px;color:#f5cf72;text-align:center;text-shadow:0 5px 0 #06121f,0 0 30px rgba(245,207,114,.35)}}
.part-badge{{position:absolute;z-index:4;left:50%;top:312px;transform:translateX(-50%);width:250px;height:56px;font-size:30px;font-weight:900;letter-spacing:4px;color:#f5cf72;border:3px solid rgba(245,207,114,.5);border-radius:28px;background:rgba(6,18,31,.65);padding:0}}
.qlabel{{position:absolute;z-index:4;left:{CONTENT_LEFT_PX}px;top:398px;width:270px;height:56px;font-size:36px;letter-spacing:2px;color:#f5cf72;font-weight:900;justify-content:flex-start;padding:0;text-align:left;text-shadow:0 4px 0 #06121f}}
.qdiff{{position:absolute;z-index:4;left:336px;top:402px;width:120px;height:46px;font-size:24px;font-weight:900;border-radius:23px;padding:0;letter-spacing:1px}}
.timer-track{{position:absolute;z-index:4;left:{CONTENT_LEFT_PX}px;top:720px;width:{TIMER_WIDTH_PX}px;height:22px;border-radius:11px;background:rgba(255,255,255,.12);padding:0}}
.timer-fill{{position:absolute;z-index:5;left:{CONTENT_LEFT_PX}px;top:720px;height:22px;border-radius:11px;padding:0}}
.slot-num{{position:absolute;z-index:6;color:rgba(245,207,114,.85);font-size:32px;font-weight:900;justify-content:flex-start;padding:0;text-align:left}}
.slot-num-active{{position:absolute;z-index:7;color:#fff;font-size:36px;font-weight:900;justify-content:flex-start;padding:0;text-align:left;text-shadow:0 0 20px rgba(245,207,114,.9)}}
.slot-box{{position:absolute;z-index:5;border-radius:16px;border:3px solid rgba(140,170,210,.22);background:rgba(8,22,42,.55);align-items:center;justify-content:flex-start;padding:0 18px;overflow:hidden}}
.slot-box-active{{border-color:#f5cf72;background:rgba(26,46,76,.6);box-shadow:0 0 28px rgba(245,207,114,.3)}}
.slot-box-done{{border-color:rgba(120,220,165,.55);background:rgba(8,22,42,.85);color:#fff;font-weight:800;text-align:left;line-height:1.15}}
.hook{{top:50%;left:{CONTENT_LEFT_PX}px;width:{CONTENT_WIDTH_PX}px;height:90px;font-size:46px;color:#f5cf72;font-weight:900;text-align:center;letter-spacing:3px;text-transform:uppercase}}
.cta{{position:absolute;z-index:4;left:50%;top:1420px;transform:translateX(-50%);width:860px;height:96px;font-size:36px;font-weight:900;letter-spacing:2px;color:#f5cf72;border:3px solid rgba(245,207,114,.6);border-radius:48px;background:rgba(6,18,31,.7);padding:0;text-transform:uppercase}}
.cta-sub{{position:absolute;z-index:4;left:{CONTENT_LEFT_PX}px;top:1540px;width:{CONTENT_WIDTH_PX}px;height:56px;font-size:26px;color:#d7e6ff;text-align:center;letter-spacing:1px}}
.watermark{{position:absolute;top:24px;left:50%;width:22%;transform:translateX(-50%);opacity:0.82;z-index:8;filter:drop-shadow(0 8px 18px rgba(0,0,0,.35))}}
</style>
</head>
<body>
<div id="root" class="{"tracker-layout" if tracker else ""}" data-composition-id="{part_id}" data-start="0" data-width="{VIDEO_WIDTH}" data-height="{VIDEO_HEIGHT}" data-duration="{cursor:.3f}">
{''.join(elements)}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
window.__timelines["{part_id}"] = tl;
tl.seek(0);
</script>
</body>
</html>"""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "index.html").write_text(html, encoding="utf-8")
    meta = {"name": f"World General Knowledge Quiz Part {part}", "id": part_id, "fps": VIDEO_FPS, "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT, "duration_seconds": round(cursor, 2)}
    (project_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    # A minimal composition timeline. Playlist visibility is framework-driven by data-*.
    timeline = {
        "duration": round(cursor, 3),
        "audio_durations": audio_durations,
    }
    return project_dir, cursor, timeline


def _validate_rendered_video(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Rendered video is missing or empty: {path}")
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    if (stream["width"], stream["height"]) != (VIDEO_WIDTH, VIDEO_HEIGHT):
        raise RuntimeError(f"Rendered video has invalid resolution: {stream['width']}x{stream['height']}")
    if stream["r_frame_rate"] != f"{VIDEO_FPS}/1":
        raise RuntimeError(f"Rendered video has invalid frame rate: {stream['r_frame_rate']}")
    if float(payload["format"]["duration"]) <= 0:
        raise RuntimeError(f"Rendered video has invalid duration: {payload['format']['duration']}")


def render_video(project_dir, part_number, output_path=None, output_root=None):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        raise RuntimeError("Node.js/npm (npx) was not found. Install Node.js, then install HyperFrames in this project.")
    if output_path is None:
        root = Path(output_root) if output_root is not None else OUTPUT_DIR
        output_path = root / f"part_{part_number:03d}" / "video" / f"world_general_knowledge_quiz_part_{part_number:03d}.mp4"
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path = output_path.with_name(output_path.stem + ".raw.mp4")
    if rendered_path.exists():
        rendered_path.unlink()
    subprocess.run(
        [npx, "hyperframes", "render", "--output", str(rendered_path), "--fps", str(VIDEO_FPS)],
        cwd=str(project_dir), check=True
    )
    _validate_rendered_video(rendered_path)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to normalize the rendered MP4 audio for Facebook Reels.")
    normalized_path = output_path.with_name(output_path.stem + ".normalized.mp4")
    if normalized_path.exists():
        normalized_path.unlink()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(rendered_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "320k",
            "-movflags",
            "+faststart",
            str(normalized_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    _validate_rendered_video(normalized_path)
    os.replace(normalized_path, output_path)
    try:
        rendered_path.unlink()
    except OSError:
        pass
    _validate_rendered_video(output_path)
    return output_path