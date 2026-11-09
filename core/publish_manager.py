"""Manage durable publication history independently from quiz history."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = None

def _project_root():
    if PROJECT_ROOT is not None:
        return PROJECT_ROOT
    from config import PROJECT_ROOT as default_root

    return default_root


class PublishHistoryError(Exception):
    """Raised when a publication history file cannot be used."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_history(history: Any) -> dict[str, Any]:
    if not isinstance(history, dict):
        raise PublishHistoryError("Publication history must be a JSON object.")
    records = history.get("records", [])
    if not isinstance(records, list):
        raise PublishHistoryError("Publication records must be a list.")
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise PublishHistoryError(f"Publication record {index} is not a JSON object.")
    valid_content_types = {"reel", "full_video", "ten_question_video"}
    for index, record in enumerate(records, 1):
        if "content_type" not in record or record.get("content_type") not in valid_content_types:
            filename = str(record.get("video_file_name", ""))
            if filename.endswith("_reel.mp4"):
                record["content_type"] = "reel"
            elif filename.endswith("_10_questions.mp4"):
                record["content_type"] = "ten_question_video"
            else:
                record["content_type"] = "full_video"

    schema_version = history.get("schema_version", 1)
    try:
        schema_version = int(schema_version)
    except (TypeError, ValueError) as exc:
        raise PublishHistoryError("Publication history schema_version must be an integer.") from exc
    return {"schema_version": schema_version, "records": records}


def load_publish_history(history_path: Path | None = None) -> dict[str, Any]:

    path = history_path or _project_root() / "data" / "facebook_publish_history.json"
    if not path.exists():
        return {"schema_version": 1, "records": []}
    try:
        return normalize_history(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        raise PublishHistoryError(f"Publication history could not be read: {path}: {exc}") from exc


def atomic_json_write(path: Path, history: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_history(history)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            json.dump(normalized, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        except OSError:
            pass
    return path


def save_publish_history(history: Any, history_path: Path | None = None) -> Path:

    path = history_path or _project_root() / "data" / "facebook_publish_history.json"
    return atomic_json_write(path, history)


def sha256_file(video_path: Path) -> str:
    if not video_path.is_file():
        raise PublishHistoryError(f"Video file does not exist: {video_path}")
    digest = hashlib.sha256()
    with video_path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_record(history: dict[str, Any], *, part_number: int | None = None, content_hash: str | None = None, content_type: str | None = None) -> dict[str, Any] | None:
    for record in reversed(history.get("records", [])):
        if part_number is not None and record.get("part_number") != part_number:
            continue
        if content_hash is not None and record.get("content_hash") != content_hash:
            continue
        if content_type is not None and record.get("content_type") != content_type:
            continue
        return record
    return None


def _record_content_type(record: dict[str, Any]) -> str:
    content_type = record.get("content_type")
    if content_type in {"reel", "full_video", "ten_question_video"}:
        return content_type
    filename = str(record.get("video_file_name", ""))
    basename = Path(filename).name
    if basename.endswith("_reel.mp4"):
        return "reel"
    if basename.endswith("_10_questions.mp4"):
        return "ten_question_video"
    return "full_video"


def upsert_record(history_path: Path, record: dict[str, Any]) -> None:
    history = load_publish_history(history_path)
    records = history.get("records", [])
    record = {**record, "content_type": _record_content_type(record)}
    existing_index = None
    for index, current in enumerate(records):
        current_type = _record_content_type(current)
        if (
            current.get("part_number") == record.get("part_number")
            and current.get("content_hash") == record.get("content_hash")
            and current_type == record.get("content_type")
        ):
            existing_index = index
            break
    if existing_index is None:
        records.append(record)
    else:
        records[existing_index] = {**records[existing_index], **record}
    history["records"] = records
    save_publish_history(history, history_path)


@dataclass(frozen=True)
class PublishManager:
    history_path: Path | None = None

    def load(self) -> dict[str, Any]:
        return load_publish_history(self.history_path)

    def find(self, part_number: int | None = None, content_hash: str | None = None, content_type: str | None = None) -> dict[str, Any] | None:
        return find_record(self.load(), part_number=part_number, content_hash=content_hash, content_type=content_type)

    def find_record(self, part_number: int | None = None, content_hash: str | None = None, content_type: str | None = None) -> dict[str, Any] | None:
        return self.find(part_number=part_number, content_hash=content_hash, content_type=content_type)

    def record(self, record: dict[str, Any]) -> dict[str, Any]:
        upsert_record(self.history_path, record)
        return self.load()

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        atomic_json_write(path, payload)


    def upsert_record(self, record):
        upsert_record(self.history_path, record)
        return self.load()

FacebookPublishManager = PublishManager

