"""Prepare Facebook Reels publishing data without performing live uploads.

Phase 1 of the publishing architecture intentionally performs preflight
validation, dry-run payload generation, and publication-record storage only.
No Meta Graph API upload or publish request is made by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc).isoformat()
from pathlib import Path
from typing import Any

import shutil
import subprocess

from core.publish_manager import PublishHistoryError, load_publish_history, save_publish_history
from config import (
    FACEBOOK_PUBLISH_DRY_RUN,
    META_GRAPH_API_VERSION,
    META_PAGE_ID,
    META_PAGE_ACCESS_TOKEN,
    META_PUBLISH_TIMEOUT_SECONDS,
)


class FacebookPublisherError(Exception):
    """Base error for local Facebook publishing preparation."""


@dataclass(frozen=True)
class VideoPreflightResult:
    success: bool
    errors: tuple[str, ...]
    details: dict[str, Any]


@dataclass(frozen=True)
class DryRunReport:
    success: bool
    part_number: int
    video_path: str
    content_hash: str
    preflight: dict[str, Any]
    publication_status: str
    dry_run_payload: dict[str, Any]
    report_path: str


@dataclass(frozen=True)
class PublisherConfiguration:
    graph_api_version: str
    page_id: str
    access_token: str
    publish_enabled: bool
    timeout_seconds: int
    dry_run: bool

    def validate(self) -> tuple[str, ...]:
        errors = []
        if self.publish_enabled and not self.access_token:
            errors.append("META_PAGE_ACCESS_TOKEN is required when publishing is enabled.")
        if self.publish_enabled and not self.page_id:
            errors.append("META_PAGE_ID is required when publishing is enabled.")
        if not self.graph_api_version.startswith("v"):
            errors.append("META_GRAPH_API_VERSION must start with 'v'.")
        if self.timeout_seconds <= 0:
            errors.append("META_PUBLISH_TIMEOUT_SECONDS must be greater than zero.")
        return tuple(errors)


def _run_ffprobe(video_path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise FacebookPublisherError("ffprobe was not found, so video preflight validation cannot be performed.")

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate,bit_rate",
                "-show_entries",
                "format=duration,bit_rate",
                "-of",
                "json",
                str(video_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise FacebookPublisherError(f"Invalid video output for preflight validation: {video_path}") from exc

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FacebookPublisherError(f"ffprobe returned invalid JSON for {video_path}") from exc


def _frame_rate(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{int(value)}/1"
    return str(value)


class FacebookPublisher:
    """Local Phase 1 publisher for Facebook Reels.

    Phase 1 is intentionally limited to dry-run payload preparation and local
    validation. No Meta HTTP upload or publish request is sent.
    """

    def __init__(
        self,
        *,
        graph_api_version: str = META_GRAPH_API_VERSION,
        page_id: str = META_PAGE_ID,
        access_token: str = META_PAGE_ACCESS_TOKEN,
        publish_enabled: bool = False,
        dry_run: bool = FACEBOOK_PUBLISH_DRY_RUN,
        timeout_seconds: int = META_PUBLISH_TIMEOUT_SECONDS,
    ) -> None:
        self.graph_api_version = graph_api_version
        self.page_id = page_id
        self.access_token = access_token
        self.publish_enabled = publish_enabled
        self.dry_run = dry_run
        self.timeout_seconds = timeout_seconds
        self.configuration = PublisherConfiguration(
            graph_api_version=graph_api_version,
            page_id=page_id,
            access_token=access_token,
            publish_enabled=publish_enabled,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def from_environment(cls, dry_run: bool | None = None) -> "FacebookPublisher":
        return cls(
            dry_run=FACEBOOK_PUBLISH_DRY_RUN if dry_run is None else dry_run,
        )

    def _streams(self, probe: dict[str, Any], codec_type: str) -> list[dict[str, Any]]:
        return [stream for stream in probe.get("streams", [])
                if stream.get("codec_type") == codec_type]

    def _run_ffprobe(self, video_path: Path | str) -> dict[str, Any]:
        return _run_ffprobe(video_path)

    def validate_video(self, video_path: Path | str) -> VideoPreflightResult:
        """Validate an MP4 against the documented Facebook Reels profile."""
        path = Path(video_path)
        errors: list[str] = []
        details: dict[str, Any] = {}

        if not path.is_file():
            return VideoPreflightResult(success=False, errors=(f"Video file does not exist: {path}",), details=details)
        if path.stat().st_size == 0:
            return VideoPreflightResult(success=False, errors=(f"Video file is empty: {path}",), details=details)

        try:
            probe = _run_ffprobe(path)
        except FacebookPublisherError as exc:
            return VideoPreflightResult(success=False, errors=(str(exc),), details=details)

        streams = probe.get("streams", [])
        video_stream = self._streams(probe, "video")[0] if self._streams(probe, "video") else None
        audio_stream = self._streams(probe, "audio")[0] if self._streams(probe, "audio") else None

        details = {
            "video_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "video_codec": video_stream.get("codec_name") if video_stream else None,
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
            "width": video_stream.get("width") if video_stream else None,
            "height": video_stream.get("height") if video_stream else None,
            "frame_rate": _frame_rate(video_stream.get("r_frame_rate")) if video_stream else None,
            "sample_rate": int(audio_stream["sample_rate"]) if audio_stream and audio_stream.get("sample_rate") else None,
            "channels": int(audio_stream["channels"]) if audio_stream and audio_stream.get("channels") else None,
            "audio_bitrate": int(audio_stream["bit_rate"]) if audio_stream and audio_stream.get("bit_rate") else None,
            "duration_seconds": float(probe.get("format", {}).get("duration", 0)),
        }

        if video_stream is None:
            errors.append("Video stream is missing.")
        if audio_stream is None:
            errors.append("Audio stream is missing.")

        if video_stream is not None:
            if video_stream.get("codec_name") != "h264":
                errors.append(f"Video codec is {video_stream.get('codec_name')!r}; expected 'h264'.")
            if int(video_stream.get("width", 0)) != 1080:
                errors.append(f"Video width is {video_stream.get('width')}; expected 1080.")
            if int(video_stream.get("height", 0)) != 1920:
                errors.append(f"Video height is {video_stream.get('height')}; expected 1920.")
            if _frame_rate(video_stream.get("r_frame_rate")) != "30/1":
                errors.append(f"Frame rate is {video_stream.get('r_frame_rate')}; expected 30/1.")

        if audio_stream is not None:
            if audio_stream.get("codec_name") != "aac":
                errors.append(f"Audio codec is {audio_stream.get('codec_name')!r}; expected 'aac'.")
            if int(audio_stream.get("channels", 0)) != 2:
                errors.append(f"Audio channel count is {audio_stream.get('channels')}; expected 2.")
            if int(audio_stream.get("sample_rate", 0)) != 48000:
                errors.append(f"Audio sample rate is {audio_stream.get('sample_rate')} Hz; expected 48000 Hz.")
            if audio_stream.get("bit_rate") is None or int(audio_stream["bit_rate"]) < 128000:
                errors.append("Audio bitrate is below 128000 bits per second.")

        duration = float(probe.get("format", {}).get("duration", 0) or 0)
        if duration <= 0:
            errors.append("Video duration must be greater than zero.")

        errors.extend(self.configuration.validate())
        return VideoPreflightResult(success=not errors, errors=tuple(errors), details=details)

    def calculate_content_hash(self, video_path: Path | str) -> str:
        return hashlib.sha256(Path(video_path).read_bytes()).hexdigest()

    def build_reel_payload(self, part_number: int, video_path: Path | str, title: str, description: str) -> dict[str, Any]:
        return {
            "endpoint": f"https://graph.facebook.com/{self.graph_api_version}/{self.page_id}/video_reels",
            "method": "POST",
            "upload_phase": "start",
            "video_state": "PUBLISHED",
            "title": title,
            "description": description,
            "policy": "dry_run_only_in_phase_1",
            "access_token": "[redacted]",
            "metadata": {
                "part_number": part_number,
                "content_hash": self.calculate_content_hash(video_path),
            },
        }

    def run_dry_run(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        publish_manager,
    ) -> DryRunReport:
        path = Path(video_path)
        preflight = self.validate_video(path)
        content_hash = ""
        try:
            content_hash = self.calculate_content_hash(path)
        except OSError:
            content_hash = ""

        payload = self.build_reel_payload(part_number, path, title, description)
        publication_status = "dry_run" if preflight.success else "failed"
        record = {
            "part_number": part_number,
            "video_file_name": path.name,
            "content_hash": content_hash,
            "title": title,
            "description": description,
            "status": publication_status,
            "meta_graph_api_version": self.graph_api_version,
            "meta_video_id": None,
            "meta_post_id": None,
            "upload_phase": "not_started",
            "errors": list(preflight.errors),
            "created_at": _utc_now(),
            "published_at": None,
        }

        try:
            publish_manager.upsert_record(record)
        except PublishHistoryError:
            # Preflight and payload information can still be reported locally.
            pass

        report_path = path.parent / "publish" / "facebook_reels_dry_run.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "part_number": part_number,
            "video_path": str(path),
            "content_hash": content_hash,
            "preflight": {
                "success": preflight.success,
                "errors": list(preflight.errors),
                "details": preflight.details,
            },
            "publication_status": publication_status,
            "dry_run_payload": payload,
            "timestamp": _utc_now(),
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        return DryRunReport(
            success=preflight.success,
            part_number=part_number,
            video_path=str(path),
            content_hash=content_hash,
            preflight={"success": preflight.success, "errors": list(preflight.errors), "details": preflight.details},
            publication_status=publication_status,
            dry_run_payload=payload,
            report_path=str(report_path),
        )

    def publish(self, video_path: Path | str, title: str, description: str) -> dict[str, Any]:
        """Reserved for later implementation. Phase 1 is dry-run only."""
        raise NotImplementedError("Real Facebook publishing is not enabled in Phase 1.")
