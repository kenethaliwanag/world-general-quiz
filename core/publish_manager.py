"""Manage Facebook publication state separately from quiz-question history."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT


class PublishHistoryError(Exception):
    """Raised when the publication history file is missing or malformed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_history(history: Any) -> dict[str, Any]:
    if not isinstance(history, dict):
        raise PublishHistoryError("Publication history must be a JSON object.")

    records = history.get("records", [])
    if not isinstance(records, list):
        raise PublishHistoryError("Publication records must be a list.")

    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise PublishHistoryError(f"Publication record {index} must be a JSON object.")

    schema_version = history.get("schema_version", 1)
    try:
        schema_version = int(schema_version)
    except (TypeError, ValueError) as exc:
        raise PublishHistoryError("Publication history schema_version must be an integer.") from exc

    return {"schema_version": schema_version, "records": records}


def load_publish_history(history_path: Path | None = None) -> dict[str, Any]:
    """Load the publication history, or create an empty validated default."""
    path = history_path or (PROJECT_ROOT / "data" / "facebook_publish_history.json")
    if not path.exists():
        return {"schema_version": 1, "records": []}
    try:
        return _normalize_history(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        raise PublishHistoryError(f"Could not read publication history {path}: {exc}") from exc


def save_publish_history(history: dict[str, Any], history_path: Path | None = None) -> Path:
    """Atomically write a normalized publication history."""
    path = history_path or (PROJECT_ROOT / "data" / "facebook_publish_history.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_history(history)

    handle, temp_name = tempfile.mkstemp(prefix=".facebook_publish_history_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(normalized, file, indent=2, ensure_ascii=False)
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


def sha256_file(video_path: Path) -> str:
    """Calculate a SHA-256 digest for the supplied file."""
    if not video_path.is_file():
        raise PublishHistoryError(f"Video file does not exist: {video_path}")
    digest = hashlib.sha256()
    with video_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FacebookPublishManager:
    """A small wrapper to make publication records easy to test and use."""

    def __init__(self, history_path: Path | None = None) -> None:
        self.history_path = history_path or (PROJECT_ROOT / "data" / "facebook_publish_history.json")

    def load(self) -> dict[str, Any]:
        return load_publish_history(self.history_path)

    def save(self, history: dict[str, Any]) -> Path:
        return save_publish_history(history, self.history_path)

    def find_record(self, *, part_number: int, content_hash: str):
        for record in reversed(load_publish_history(self.history_path).get("records", [])):
            if record.get("part_number") == part_number and record.get("content_hash") == content_hash:
                return record
        return None

    def upsert_record(self, record: dict[str, Any]) -> dict[str, Any]:
        history = self.load()
        key = (record.get("part_number"), record.get("content_hash"))
        updated = False
        for index, existing in enumerate(history["records"]):
            if (existing.get("part_number"), existing.get("content_hash")) == key:
                history["records"][index] = {**existing, **record}
                updated = True
                break
        if not updated:
            history["records"].append(record)
        self.save(history)
        return history
