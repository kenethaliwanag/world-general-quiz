"""Phase 1 local Facebook Reels publishing foundation.

Phase 1 is intentionally dry-run only. It validates media, builds a redacted
publication payload, manages publication history, and does not contact Meta.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FacebookPublisherError(Exception):
    """Raised when local Facebook publishing preparation cannot proceed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frame_rate(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (int, float)):
        return f"{int(value)}/1"
    return str(value)


def _run_ffprobe(video_path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise FacebookPublisherError("ffprobe is required for Facebook Reels preflight validation.")
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate,bit_rate",
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
            timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise FacebookPublisherError(f"Could not probe video metadata for {video_path}.") from exc
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FacebookPublisherError(f"ffprobe returned invalid JSON for {video_path}.") from exc


@dataclass(frozen=True)
class VideoPreflightResult:
    success: bool
    errors: tuple[str, ...]
    details: dict[str, Any]


@dataclass(frozen=True)
class DryRunReport:
    success: bool
    dry_run: bool
    part_number: int
    video_path: str
    content_hash: str
    preflight: dict[str, Any]
    publication_status: str
    dry_run_payload: dict[str, Any]
    report_path: str


class FacebookPublisher:
    """Local, standard-library-only Facebook Reels publisher foundation."""

    def __init__(
        self,
        graph_api_version: str | None = None,
        dry_run: bool = True,
        timeout_seconds: int = 120,
        page_id: str | None = None,
        access_token: str | None = None,
    ) -> None:
        from config import (
            FACEBOOK_PUBLISH_DRY_RUN,
            FACEBOOK_PUBLISH_ENABLED,
            META_GRAPH_API_VERSION,
            META_PAGE_ACCESS_TOKEN,
            META_PAGE_ID,
            META_PUBLISH_TIMEOUT_SECONDS,
        )

        self.graph_api_version = graph_api_version or META_GRAPH_API_VERSION
        self.dry_run = dry_run if dry_run is not None else FACEBOOK_PUBLISH_DRY_RUN
        self.publish_enabled = FACEBOOK_PUBLISH_ENABLED
        self.timeout_seconds = int(timeout_seconds if timeout_seconds else META_PUBLISH_TIMEOUT_SECONDS)
        self.page_id = page_id if page_id is not None else META_PAGE_ID
        self.access_token = access_token if access_token is not None else META_PAGE_ACCESS_TOKEN

    def _streams(self, probe: dict[str, Any], codec_type: str) -> list[dict[str, Any]]:
        return [stream for stream in probe.get("streams", []) if stream.get("codec_type") == codec_type]

    def validate_configuration(self) -> tuple[str, ...]:
        errors = []
        if not self.page_id:
            errors.append("META_PAGE_ID is not configured.")
        if not self.access_token:
            errors.append("META_PAGE_ACCESS_TOKEN is not configured.")
        if not self.graph_api_version.startswith("v"):
            errors.append("META_GRAPH_API_VERSION must begin with 'v'.")
        if self.timeout_seconds <= 0:
            errors.append("META_PUBLISH_TIMEOUT_SECONDS must be greater than zero.")
        return tuple(errors)

    def validate_video(self, video_path: Path | str) -> VideoPreflightResult:
        """Validate a Part against the Facebook Reels technical profile."""
        path = Path(video_path)
        errors: list[str] = []
        details: dict[str, Any] = {}

        if not path.is_file():
            return VideoPreflightResult(success=False, errors=(f"Video file does not exist: {path}",), details=details)
        if path.stat().st_size == 0:
            return VideoPreflightResult(success=False, errors=(f"Video file is empty: {path}",), details=details)

        probe = _run_ffprobe(path)
        video_streams = self._streams(probe, "video")
        audio_streams = self._streams(probe, "audio")
        video = video_streams[0] if video_streams else None
        audio = audio_streams[0] if audio_streams else None

        details = {
            "video_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "video_codec": video.get("codec_name") if video else None,
            "audio_codec": audio.get("codec_name") if audio else None,
            "width": int(video["width"]) if video and "width" in video else None,
            "height": int(video["height"]) if video and "height" in video else None,
            "frame_rate": _frame_rate(video.get("r_frame_rate")) if video else None,
            "audio_sample_rate": int(audio["sample_rate"]) if audio and "sample_rate" in audio else None,
            "audio_channels": int(audio["channels"]) if audio and "channels" in audio else None,
            "audio_bitrate": int(audio["bit_rate"]) if audio and audio.get("bit_rate") is not None else None,
            "duration_seconds": float(probe.get("format", {}).get("duration", 0) or 0),
        }

        if video is None:
            errors.append("The MP4 must contain a video stream.")
        else:
            if video.get("codec_name") != "h264":
                errors.append(f"Video codec is {video.get('codec_name')!r}; expected 'h264'.")
            if int(video.get("width", 0)) != 1080:
                errors.append(f"Video width is {video.get('width')}; expected 1080.")
            if int(video.get("height", 0)) != 1920:
                errors.append(f"Video height is {video.get('height')}; expected 1920.")
            if _frame_rate(video.get("r_frame_rate")) != "30/1":
                errors.append(f"Frame rate is {video.get('r_frame_rate')}; expected 30/1.")

        if audio is None:
            errors.append("The MP4 must contain an audio stream.")
        else:
            if audio.get("codec_name") != "aac":
                errors.append(f"Audio codec is {audio.get('codec_name')!r}; expected 'aac'.")
            if int(audio.get("channels", 0)) != 2:
                errors.append(f"Audio channel count is {audio.get('channels')}; expected 2.")
            if int(audio.get("sample_rate", 0)) != 48000:
                errors.append(f"Audio sample rate is {audio.get('sample_rate')} Hz; expected 48000 Hz.")
            if audio.get("bit_rate") is None:
                errors.append("ffprobe did not report an audio bitrate.")
            elif int(audio["bit_rate"]) < 128000:
                errors.append(f"Audio bitrate is {audio['bit_rate']} bps; expected at least 128000 bps.")

        if details["duration_seconds"] <= 0:
            errors.append("Video duration must be greater than zero.")
        if details["duration_seconds"] < 3 or details["duration_seconds"] > 90:
            errors.append(
                f"Video duration is {details['duration_seconds']:.3f} seconds; "
                "Meta expects a Reel duration between 3 and 90 seconds."
            )

        if self.publish_enabled:
            errors.extend(self.validate_configuration())

        return VideoPreflightResult(success=not errors, errors=tuple(errors), details=details)

    def calculate_content_hash(self, video_path: Path | str) -> str:
        path = Path(video_path)
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def build_reel_payload(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        content_hash: str,
    ) -> dict[str, Any]:
        video_path = Path(video_path)
        return {
            "endpoint": f"https://graph.facebook.com/{self.graph_api_version}/<page_id>/video_reels",
            "method": "POST",
            "phase_1_mode": "dry_run",
            "title": title,
            "description": description,
            "upload_phase": "start",
            "access_token": "[redacted]",
            "metadata": {
                "content_hash": content_hash,
                "part_number": part_number,
            },
            "params": {
                "upload_phase": "start",
                "upload_phase_finish": "finish",
                "video_state": "PUBLISHED",
                "video_id": "<returned by Meta upload initializer>",
                "title": title,
                "description": description,
                "content_hash": content_hash,
                "part_number": part_number,
                "access_token": "[redacted]",
            },
            "live_calls": "Disabled in Phase 1",
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
        content_hash = self.calculate_content_hash(path)
        payload = self.build_reel_payload(part_number, path, title, description, content_hash)
        status = "dry_run" if preflight.success else "failed"

        record = {
            "part_number": part_number,
            "video_file_name": path.name,
            "content_hash": content_hash,
            "title": title,
            "description": description,
            "status": status,
            "meta_graph_api_version": self.graph_api_version,
            "meta_video_id": None,
            "meta_post_id": None,
            "upload_phase": "not_started",
            "errors": list(preflight.errors),
            "created_at": utc_now(),
            "published_at": None,
        }
        publish_manager.upsert_record(record)

        report_path = path.parent / "publish" / "facebook_reels_dry_run.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "part_number": part_number,
            "video_path": str(path),
            "content_hash": content_hash,
            "preflight": asdict(preflight),
            "publication_status": status,
            "dry_run_payload": payload,
            "timestamp": utc_now(),
        }
        serialize_json(report_path, report)

        return DryRunReport(
            success=preflight.success,
            dry_run=True,
            part_number=part_number,
            video_path=str(path),
            content_hash=content_hash,
            preflight=asdict(preflight),
            publication_status=status,
            dry_run_payload=payload,
            report_path=str(report_path),
        )


    def publish_reel(self, video_path: Path | str, title: str, description: str) -> dict[str, Any]:
        """Real publication is deliberately unavailable in Phase 1."""
        raise NotImplementedError("Phase 1 is dry-run only. Real Meta Graph API publishing is not implemented.")

    def from_environment(self):
        return self


def serialize_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
