"""Independent YouTube Shorts publication history.

This file is deliberately separate from ``core/publish_manager.py``: the Facebook
manager rewrites unknown ``content_type`` values, which would corrupt YouTube
records. Credentials and resumable upload session URLs are never stored here.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = None
CONTENT_TYPE = "youtube_shorts"  # backward-compatible default
CONTENT_TYPES = {"youtube_shorts", "youtube_ten_question_video"}
VALID_UPLOAD_STATUSES = {"dry_run", "uploading", "uploaded", "failed"}
BLOCKING_UPLOAD_STATUSES = {"uploading", "uploaded"}
CREDENTIAL_KEY_MARKERS = ("token", "secret", "session", "authorization", "password")


class YouTubePublishHistoryError(Exception):
    """Raised when the YouTube publication history cannot be used safely."""


def _project_root() -> Path:
    if PROJECT_ROOT is not None:
        return Path(PROJECT_ROOT)
    from config import PROJECT_ROOT as default_root

    return default_root


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_history_path() -> Path:
    return _project_root() / "data" / "youtube_publish_history.json"


def normalize_history(history: Any) -> dict[str, Any]:
    if not isinstance(history, dict):
        raise YouTubePublishHistoryError("YouTube publication history must be a JSON object.")
    records = history.get("records", [])
    if not isinstance(records, list):
        raise YouTubePublishHistoryError("YouTube publication records must be a list.")
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise YouTubePublishHistoryError(f"YouTube publication record {index} is not a JSON object.")
        if record.get("content_type", CONTENT_TYPE) not in CONTENT_TYPES:
            raise YouTubePublishHistoryError(f"YouTube publication record {index} has an invalid content type.")
        status = record.get("upload_status")
        if status is not None and status not in VALID_UPLOAD_STATUSES:
            raise YouTubePublishHistoryError(f"YouTube publication record {index} has an invalid upload status.")
    schema_version = history.get("schema_version", 1)
    try:
        schema_version = int(schema_version)
    except (TypeError, ValueError) as exc:
        raise YouTubePublishHistoryError("schema_version must be an integer.") from exc
    return {"schema_version": schema_version, "records": records}


def load_publish_history(history_path: Path | None = None) -> dict[str, Any]:
    path = history_path or default_history_path()
    if not path.exists():
        return {"schema_version": 1, "records": []}
    try:
        return normalize_history(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        raise YouTubePublishHistoryError(f"YouTube publication history could not be read: {path}: {exc}") from exc


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}
    for key, value in record.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in CREDENTIAL_KEY_MARKERS):
            continue
        cleaned[key] = value
    return cleaned


def atomic_json_write(path: Path, history: Any) -> Path:
    path = Path(path)
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
    return atomic_json_write(history_path or default_history_path(), history)


def sha256_file(video_path: Path | str) -> str:
    path = Path(video_path)
    if not path.is_file():
        raise YouTubePublishHistoryError(f"Video file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_record(
    history: dict[str, Any],
    *,
    part_number: int | None = None,
    content_hash: str | None = None,
    upload_status: str | None = None,
    content_type: str | None = None,
) -> dict[str, Any] | None:
    for record in reversed(history.get("records", [])):
        if part_number is not None and record.get("part_number") != part_number:
            continue
        if content_hash is not None and record.get("content_hash") != content_hash:
            continue
        if upload_status is not None and record.get("upload_status") != upload_status:
            continue
        if content_type is not None and record.get("content_type", CONTENT_TYPE) != content_type:
            continue
        return record
    return None


def is_duplicate(
    history: dict[str, Any],
    part_number: int,
    content_hash: str,
    content_type: str | None = None,
) -> bool:
    """True when a matching upload of the same content type exists or is in progress."""
    return any(
        record.get("part_number") == part_number
        and record.get("content_hash") == content_hash
        and record.get("content_type", CONTENT_TYPE) == (content_type or CONTENT_TYPE)
        and record.get("upload_status") in BLOCKING_UPLOAD_STATUSES
        for record in history.get("records", [])
    )


def upsert_record(history_path: Path, record: dict[str, Any]) -> None:
    cleaned = _sanitize_record(record)
    cleaned.setdefault("content_type", CONTENT_TYPE)
    if cleaned["content_type"] not in CONTENT_TYPES:
        raise YouTubePublishHistoryError(f"Invalid content type: {cleaned['content_type']}")
    history = load_publish_history(history_path)
    records = history.get("records", [])
    existing_index = next(
        (
            index
            for index, current in enumerate(records)
            if current.get("part_number") == cleaned.get("part_number")
            and current.get("content_hash") == cleaned.get("content_hash")
            and current.get("content_type", CONTENT_TYPE) == cleaned["content_type"]
        ),
        None,
    )
    if (
        existing_index is not None
        and records[existing_index].get("upload_status") == "failed"
        and cleaned.get("upload_status") == "uploaded"
    ):
        # Keep the failed attempt as history; a successful retry gets its own record.
        existing_index = None
    if existing_index is None:
        records.append(cleaned)
    else:
        records[existing_index] = {**records[existing_index], **cleaned}
    history["records"] = records
    save_publish_history(history, history_path)


@dataclass(frozen=True)
class YouTubePublishManager:
    history_path: Path | None = None

    def path(self) -> Path:
        return self.history_path or default_history_path()

    def load(self) -> dict[str, Any]:
        return load_publish_history(self.history_path)

    def find(
        self,
        *,
        part_number: int | None = None,
        content_hash: str | None = None,
        upload_status: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any] | None:
        return find_record(
            self.load(),
            part_number=part_number,
            content_hash=content_hash,
            upload_status=upload_status,
            content_type=content_type,
        )

    def is_duplicate(self, part_number: int, content_hash: str, content_type: str | None = None) -> bool:
        return is_duplicate(self.load(), part_number, content_hash, content_type)

    def record(self, record: dict[str, Any]) -> dict[str, Any]:
        upsert_record(self.path(), record)
        return self.load()
