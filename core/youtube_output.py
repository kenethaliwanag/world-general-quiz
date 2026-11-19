"""YouTube-only output paths and independent Part numbering.

Facebook keeps its existing ``output/part_XXX`` layout. YouTube uses its own root
and starts at Part 1, independent of ``data/used_questions.json``'s ``last_part``.
"""
from __future__ import annotations

import json
from pathlib import Path

from config import OUTPUT_DIR


YOUTUBE_OUTPUT_SUBDIR = "youtube"
SHORTS_SUBDIRS = ("youtube", "shorts")
SHORTS_FILENAME = "world_general_knowledge_quiz_part_{part:03d}.mp4"
TEN_QUESTION_SUBDIRS = ("youtube", "videos")
TEN_QUESTION_FILENAME = "world_general_knowledge_quiz_part_{part:03d}_10_questions.mp4"
SHORTS_CONTENT_TYPE = "youtube_shorts"
TEN_QUESTION_CONTENT_TYPE = "youtube_ten_question_video"
OCCUPIED_STATUSES = {"uploaded", "uploading"}


def youtube_output_root(output_root=None) -> Path:
    if output_root is not None and str(output_root).strip():
        return Path(output_root)
    return OUTPUT_DIR / YOUTUBE_OUTPUT_SUBDIR


def youtube_part_dir(part_number: int, output_root=None) -> Path:
    return youtube_output_root(output_root) / f"part_{int(part_number):03d}"


def youtube_shorts_path(part_number: int, output_root=None) -> Path:
    path = youtube_part_dir(part_number, output_root)
    for segment in SHORTS_SUBDIRS:
        path /= segment
    return path / SHORTS_FILENAME.format(part=int(part_number))


def youtube_ten_question_video_path(part_number: int, output_root=None) -> Path:
    """Path for the 10-question tracker video; never reuses the Shorts path."""
    path = youtube_part_dir(part_number, output_root)
    for segment in TEN_QUESTION_SUBDIRS:
        path /= segment
    return path / TEN_QUESTION_FILENAME.format(part=int(part_number))


def _path_for_content_type(part_number: int, output_root, content_type: str) -> Path:
    if content_type == TEN_QUESTION_CONTENT_TYPE:
        return youtube_ten_question_video_path(part_number, output_root)
    return youtube_shorts_path(part_number, output_root)


def _load_records(history_path: Path) -> list[dict]:
    if not history_path.is_file():
        return []
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []
    records = payload.get("records", []) if isinstance(payload, dict) else []
    return [record for record in records if isinstance(record, dict)]


def next_youtube_part_number(
    history_path=None,
    output_root=None,
    content_type: str = SHORTS_CONTENT_TYPE,
) -> int:
    """Lowest Part available for ``content_type`` (Shorts by default).

    Only records of the requested content type reserve a number, so a 10-question
    video may reuse Part 1 even though a Shorts video already exists for Part 1.
    Failed attempts without a video ID do not reserve a number, so a retry reuses
    the same Part instead of silently consuming the next one.
    """
    path = Path(history_path) if history_path is not None else Path(__file__).resolve().parents[1] / "data" / "youtube_publish_history.json"
    reserved = set()
    retryable = set()
    for record in _load_records(path):
        if record.get("content_type", SHORTS_CONTENT_TYPE) != content_type:
            continue
        try:
            part = int(record.get("part_number"))
        except (TypeError, ValueError):
            continue
        if record.get("upload_status") in OCCUPIED_STATUSES or record.get("youtube_video_id"):
            reserved.add(part)
        elif record.get("upload_status") == "failed":
            retryable.add(part)

    root = youtube_output_root(output_root)
    if root.is_dir():
        for entry in root.glob("part_*"):
            try:
                part = int(entry.name[len("part_"):])
            except ValueError:
                continue
            # A finished video of this type is never overwritten; a failed attempt
            # may reuse its own file without regeneration. A directory holding only
            # the other content type does not reserve this Part.
            if _path_for_content_type(part, root, content_type).is_file() and part not in retryable:
                reserved.add(part)

    candidate = 1
    while candidate in reserved:
        candidate += 1
    return candidate
