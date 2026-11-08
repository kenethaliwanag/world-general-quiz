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
)
from integrations.kokoro_tts import audio_duration as measure_audio_duration


def _esc(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def _audio_duration(path, fallback=None):
    try:
        return measure_audio_duration(path)
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return fallback


def create_composition(quiz, audio_map=None, content_type="full"):
    audio_map = audio_map or {}
    part = quiz["part"]
    project_subdir = "reels" if content_type == "reel" else ""
    project_components = [OUTPUT_DIR, "hyperframes", f"part_{part:03d}"]
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
    intro_audio_duration = audio_durations.get("intro")
    if intro_audio_duration is not None:
        intro_duration = max(8.0, intro_audio_duration + AUDIO_PADDING_SECONDS)
    else:
        intro_duration = 8.0
    add_text(intro_lines[0], cursor, intro_duration, "title", "intro-title")
    add_text(intro_lines[1], cursor + 1.0, max(1.0, intro_duration - 1.0), "subtitle", "intro-subtitle")
    add_text(intro_lines[2], cursor + 3.4, max(1.0, intro_duration - 3.4), "partline", "intro-partline")
    if copied_audio.get("intro"):
        add_audio("intro", cursor, intro_audio_duration if intro_audio_duration is not None else intro_duration)
    cursor += intro_duration + TRANSITION_SECONDS

    for item in quiz["questions"]:
        n = item["number"]
        q_key, a_key = f"q{n}", f"a{n}"
        question_audio_duration = audio_durations.get(q_key)
        if question_audio_duration is not None:
            question_duration = max(3.5, question_audio_duration + AUDIO_PADDING_SECONDS)
        else:
            question_duration = 3.5
        question_visible_duration = question_duration + COUNTDOWN_SECONDS
        add_text(f"QUESTION {n:02d}", cursor, question_visible_duration, "eyebrow", f"q{n}-eyebrow")
        add_text(item["question"], cursor, question_visible_duration, "question", f"q{n}-question")
        if copied_audio.get(q_key):
            add_audio(q_key, cursor, question_audio_duration if question_audio_duration is not None else question_duration)
        countdown_start = cursor + question_duration
        for second in range(COUNTDOWN_SECONDS, 0, -1):
            tick_start = countdown_start + (COUNTDOWN_SECONDS - second)
            add_text(str(second), tick_start, 1.0, "countdown", f"q{n}-countdown-{second}")
            add_sfx(f"q{n}-{second}-tick", "tick", tick_start, SFX_TICK_VOLUME)
        timeup_start = countdown_start + COUNTDOWN_SECONDS
        add_sfx(f"q{n}-timeup", "timeup", timeup_start, SFX_TIMEUP_VOLUME)
        cursor = countdown_start + COUNTDOWN_SECONDS

        answer_audio_duration = audio_durations.get(a_key)
        if answer_audio_duration is not None:
            reveal_duration = max(ANSWER_DISPLAY_SECONDS, answer_audio_duration + AUDIO_PADDING_SECONDS)
        else:
            reveal_duration = ANSWER_DISPLAY_SECONDS
        add_text("CORRECT ANSWER", cursor, reveal_duration, "eyebrow answer-label", f"q{n}-answer-label")
        add_text(item["answer"], cursor, reveal_duration, "answer", f"q{n}-answer")
        if copied_audio.get(a_key):
            add_audio(a_key, cursor, answer_audio_duration if answer_audio_duration is not None else reveal_duration)
        cursor += reveal_duration + TRANSITION_SECONDS

    ending_audio_duration = audio_durations.get("ending")
    if ending_audio_duration is not None:
        ending_duration = max(6.0, ending_audio_duration + AUDIO_PADDING_SECONDS)
    else:
        ending_duration = 6.0
    add_text("HOW DID YOU DO?", cursor, ending_duration, "eyebrow", "ending-eyebrow")
    add_text(quiz["ending"], cursor, ending_duration, "ending", "ending-text")
    add_text(f"PART {part}", cursor + max(0.0, ending_duration - 2.5), 2.5, "partline", "ending-part")
    if copied_audio.get("ending"):
        add_audio("ending", cursor, ending_audio_duration if ending_audio_duration is not None else ending_duration)
    cursor += ending_duration

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
</style>
</head>
<body>
<div id="root" data-composition-id="{part_id}" data-start="0" data-width="{VIDEO_WIDTH}" data-height="{VIDEO_HEIGHT}" data-duration="{cursor:.3f}">
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


def render_video(project_dir, part_number, output_path=None):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        raise RuntimeError("Node.js/npm (npx) was not found. Install Node.js, then install HyperFrames in this project.")
    if output_path is None:
        output_path = OUTPUT_DIR / f"part_{part_number:03d}" / "video" / f"world_general_knowledge_quiz_part_{part_number:03d}.mp4"
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
            "192k",
            "-minrate",
            "192k",
            "-maxrate",
            "192k",
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