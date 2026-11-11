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
import time
import urllib.error
import urllib.parse
import urllib.request
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Measured average AAC bitrate: ~95 kbps with narration, ~13 kbps without it.
# shortcut: average bitrate only proxies "has narration"; switch to a mean-volume check if false positives appear.
MIN_AUDIO_BITRATE_BPS = 50000


class FacebookPublisherError(Exception):
    """Raised when local Facebook publishing preparation cannot proceed."""


class FacebookApiError(FacebookPublisherError):
    """Raised for a failed Meta Graph API request."""


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


def _error_body(self, body: bytes) -> tuple[str, int | None, str | None, str | None]:
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed = {}
    error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
    message = str(error.get("message") or body.decode("utf-8", errors="replace").strip())
    message = message.replace(self.access_token, "[redacted]") if self.access_token else message
    return message, error.get("code"), error.get("type"), error.get("fbtrace_id")


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
            META_GRAPH_API_BASE_URL,
            META_VIDEO_UPLOAD_BASE_URL,
            META_GRAPH_API_VERSION,
            META_PAGE_ACCESS_TOKEN,
            META_PAGE_ID,
            META_PUBLISH_TIMEOUT_SECONDS,
        )

        self.graph_api_version = graph_api_version or META_GRAPH_API_VERSION
        self.graph_api_base_url = META_GRAPH_API_BASE_URL.rstrip("/")
        self.video_upload_base_url = META_VIDEO_UPLOAD_BASE_URL.rstrip("/")
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

    def validate_video(self, video_path: Path | str, content_type: str = "reel") -> VideoPreflightResult:
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
            elif int(audio["bit_rate"]) < MIN_AUDIO_BITRATE_BPS:
                errors.append(
                    f"Audio bitrate is {audio['bit_rate']} bps; expected at least {MIN_AUDIO_BITRATE_BPS} bps."
                )

        if details["duration_seconds"] <= 0:
            errors.append("Video duration must be greater than zero.")
        if content_type == "reel" and (details["duration_seconds"] < 3 or details["duration_seconds"] > 90):
            errors.append(
                f"Video duration is {details['duration_seconds']:.3f} seconds; "
                "Meta expects a Reel duration between 3 and 90 seconds."
            )

        if self.publish_enabled:
            errors.extend(self.validate_configuration())

        return VideoPreflightResult(success=not errors, errors=tuple(errors), details=details)

    def _redacted_error_body(self, body: bytes, status_code: int) -> str:
        try:
            parsed = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = {}
        error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
        message = str(error.get("message") or body.decode("utf-8", errors="replace").strip())
        message = message.replace(self.access_token, "[redacted]") if self.access_token else message
        code = error.get("code")
        error_type = error.get("type")
        trace_id = error.get("fbtrace_id")
        details = [f"Meta HTTP error {status_code} during upload."]
        if code is not None:
            details.append(f"code={code}")
        if error_type:
            details.append(f"type={error_type}")
        if trace_id:
            details.append(f"trace={trace_id}")
        if message:
            details.append(f"message={message}")
        return " ".join(details)

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
        content_type: str = "reel",
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
        content_type: str = "reel",
    ) -> DryRunReport:
        path = Path(video_path)
        preflight = self.validate_video(path, content_type=content_type)
        content_hash = self.calculate_content_hash(path)
        payload = self.build_reel_payload(part_number, path, title, description, content_hash, content_type=content_type)
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
            "content_type": content_type,
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


    def _api_url(self, resource_path: str, query: dict[str, Any] | None = None) -> str:
        query = query or {}
        url = f"{self.graph_api_base_url}/{self.graph_api_version}/{resource_path.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        return url

    def _parse_response(self, raw: bytes) -> dict[str, Any]:
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {}

    def _request_json(self, method: str, url: str, payload: dict[str, Any] | None = None, query: dict[str, Any] | None = None,
                      extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        if query:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
            body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            parsed = self._parse_response(body)
            error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
            message = self._redact(str(error.get("message", body.decode("utf-8", errors="replace").strip())))
            parts = [f"Meta Graph API request failed with HTTP {exc.code}."]
            if error.get("code"):
                parts.append(f"code {error['code']}")
            if error.get("type"):
                parts.append(f"type {error['type']}")
            if error.get("fbtrace_id"):
                parts.append(f"trace {error['fbtrace_id']}")
            if message:
                parts.append(f"message: {message}")
            raise FacebookApiError(" ".join(parts)) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason or exc
            raise FacebookApiError(f"Meta Graph API network request failed: {reason}") from exc
        if not body:
            raise FacebookApiError("Meta Graph API returned an empty response.")
        parsed = self._parse_response(body)
        if not isinstance(parsed, dict):
            raise FacebookApiError("Meta Graph API returned an unexpected response.")
        return parsed

    def _request_bytes(self, url: str, payload: bytes, headers: dict[str, str] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(url, data=payload, headers=headers or {}, method="POST")
        try:
            response = urllib.request.urlopen(request, timeout=max(self.timeout_seconds, 300))
            body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            parsed = self._parse_response(body)
            error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
            message = self._redact(str(error.get("message", body.decode("utf-8", errors="replace").strip())))
            details = " ".join(part for part in (
                f"HTTP {exc.code}",
                f"code {error.get('code')}" if error.get("code") else None,
                f"type {error['type']}" if error.get("type") else None,
                f"message {message}" if message else None,
            ) if part)
            raise FacebookApiError(details or "Binary upload to Meta failed.") from exc
        except urllib.error.URLError as exc:
            raise FacebookApiError(f"Video upload connection failed: {exc.reason or exc}") from exc
        if not body:
            return {}
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"raw_response": body.decode("utf-8", errors="replace")}
        return parsed

    def _redact_url(self, value: str) -> str:
        parsed = urllib.parse.urlsplit(value)
        query = urllib.parse.parse_qsl(parsed.query)
        redacted = [
            (key, "[redacted]" if key.lower() in {"access_token", "token", "authorization"} else val)
            for key, val in query
        ]
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(redacted), parsed.fragment))

    def get_page_metadata(self) -> dict[str, Any]:
        self.validate_configuration()
        if not self.page_id or not self.access_token:
            raise FacebookPublisherError("META_PAGE_ID and META_PAGE_ACCESS_TOKEN are required to contact Meta.")
        return self._request_json(
            "GET",
            self._graph_url(self.page_id, query={"fields": "id,name,username,link,category", "access_token": self.access_token}),
        )

    def _start_upload(self, title: str, description: str) -> tuple[str, str]:
        start_data = {
            "upload_phase": "START",
            "title": title,
            "description": description,
            "access_token": self.access_token,
        }
        result = self._request_json("POST", self._graph_url(f"{self.page_id}/video_reels"), start_data)
        video_id = result.get("video_id")
        upload_url = result.get("upload_url")
        if not video_id or not upload_url:
            raise FacebookApiError("Meta did not return both video_id and upload_url for the reel upload session.")
        return str(video_id), str(upload_url)

    def _upload_video_bytes(self, upload_url: str, video_path: Path) -> dict[str, Any]:
        file_size = video_path.stat().st_size
        response = self._request_bytes(
            "POST",
            upload_url,
            video_path.read_bytes(),
            {
                "Authorization": f"OAuth {self.access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
        )
        if response.get("success") is False:
            raise FacebookApiError("Meta did not accept the reel video bytes.")
        return response

    def _finish_publish(self, video_id: str, title: str, description: str) -> dict[str, Any]:
        finish_data = {
            "access_token": self.access_token,
            "video_id": video_id,
            "upload_phase": "FINISH",
            "video_state": "PUBLISHED",
            "title": title,
            "description": description,
        }
        result = self._request_json("POST", self._graph_url(f"{self.page_id}/video_reels"), finish_data)
        if not result.get("success"):
            raise FacebookApiError("Meta accepted the upload but did not report the reel as published.")
        return result

    def _prior_published_record(self, publish_manager, content_hash: str, part_number: int):
        prior = publish_manager.find_record(part_number=part_number, content_hash=content_hash)
        if prior is not None and prior.get("status") == "published":
            return prior
        return None

    def publish_reel(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        publish_manager,
        content_type: str = "reel",
    ) -> dict[str, Any]:
        path = Path(video_path)
        content_type = content_type or "reel"
        preflight = self.validate_video(path, content_type=content_type)
        content_hash = self.calculate_content_hash(path)
        errors = self.validate_configuration()
        if errors:
            errors = tuple(errors)

        if not preflight.success or errors:
            record = {
                "part_number": part_number,
                "video_file_name": path.name,
                "content_hash": content_hash,
                "title": title,
                "description": description,
                "status": "failed",
                "meta_graph_api_version": self.graph_api_version,
                "meta_video_id": None,
                "meta_post_id": None,
                "upload_phase": "not_started",
                "errors": list(preflight.errors) + list(errors),
                "created_at": utc_now(),
                "published_at": None,
            }
            publish_manager.upsert_record(record)
            return {
                "success": False,
                "phase_2_live": True,
                "part_number": part_number,
                "content_hash": content_hash,
                "preflight": {"success": False, "errors": list(preflight.errors)},
                "errors": list(preflight.errors) + list(errors),
            }

        if not self.publish_enabled or self.dry_run:
            raise FacebookPublisherError(
                "Live Facebook publishing is disabled. Set FACEBOOK_PUBLISH_ENABLED=true and FACEBOOK_PUBLISH_DRY_RUN=false."
            )

        prior_record = self._prior_published_record(publish_manager, content_hash, part_number)
        if prior_record is not None:
            return {
                "success": True,
                "part_number": part_number,
                "content_hash": content_hash,
                "skipped": True,
                "reason": "already_published",
                "meta_video_id": prior_record.get("meta_video_id"),
                "meta_post_id": prior_record.get("meta_post_id"),
                "errors": [],
            }

        pending_record = {
            "part_number": part_number,
            "video_file_name": path.name,
            "content_hash": content_hash,
            "title": title,
            "description": description,
            "status": "publish_started",
            "meta_graph_api_version": self.graph_api_version,
            "meta_video_id": None,
            "meta_post_id": None,
            "upload_phase": "initialize",
            "errors": [],
            "content_type": content_type,
            "created_at": utc_now(),
            "published_at": None,
        }
        publish_manager.upsert_record(pending_record)

        try:
            video_id, upload_url = self._start_upload(title, description)
            upload_state = dict(pending_record)
            upload_state.update(
                {
                    "status": "uploading",
                    "meta_video_id": video_id,
                    "upload_phase": "transfer",
                    "upload_url": self._redact_url(upload_url),
                }
            )
            publish_manager.upsert_record(upload_state)

            self._upload_video(video_id, upload_url, path)

            complete_state = dict(upload_state)
            complete_state.update(
                {
                    "status": "upload_complete",
                    "upload_phase": "finish_pending",
                }
            )
            publish_manager.upsert_record(complete_state)

            final_result = self._finish_publish(video_id, title, description)

            published_record = dict(complete_state)
            published_record.update(
                {
                    "status": "published",
                    "upload_phase": "finish",
                    "meta_post_id": final_result.get("post_id") or final_result.get("video_id"),
                    "published_at": utc_now(),
                    "errors": [],
                }
            )
            publish_manager.upsert_record(published_record)
            return {
                "success": True,
                "phase_2_live": True,
                "part_number": part_number,
                "content_hash": content_hash,
                "meta_video_id": video_id,
                "meta_post_id": published_record["meta_post_id"],
                "result": final_result,
                "errors": [],
            }
        except (FacebookApiError, OSError, TimeoutError, KeyError, ValueError) as exc:
            stored_record = publish_manager.find_record(part_number=part_number, content_hash=content_hash)
            base = (stored_record or pending_record).copy()
            base.update(
                {
                    "status": "failed",
                    "errors": [str(exc)],
                    "upload_phase": "failed",
                }
            )
            publish_manager.upsert_record(base)
            raise FacebookApiError(self._redact(str(exc))) from exc

    def build_reel_payload(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        content_hash: str,
        content_type: str = "reel",
    ) -> dict[str, Any]:
        video_path = Path(video_path)
        endpoint = (
            f"{self.graph_api_base_url}/{self.graph_api_version}/<page_id>/video_reels"
            if content_type == "reel"
            else f"{self.graph_api_base_url}/{self.graph_api_version}/<page_id>/videos"
        )
        return {
            "endpoint": endpoint,
            "method": "POST",
            "phase_1_mode": "dry_run",
            "phase_2_mode": "live_when_guarded",
            "title": title,
            "description": description,
            "upload_phase": "start",
            "access_token": "[redacted]",
            "metadata": {
                "content_hash": content_hash,
                "part_number": part_number,
            },
            "params": {
                "upload_phase_start": "start",
                "upload_phase_finish": "finish",
                "video_state": "PUBLISHED",
                "video_id": "<returned by Meta upload initializer>",
                "title": title,
                "description": description,
                "content_hash": content_hash,
                "part_number": part_number,
                "access_token": "[redacted]",
            },
            "live_calls": "Enabled only when FACEBOOK_PUBLISH_ENABLED=true and FACEBOOK_PUBLISH_DRY_RUN=false",
        }

    def run_dry_run(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        publish_manager,
        content_type: str = "reel",
    ) -> DryRunReport:
        path = Path(video_path)
        preflight = self.validate_video(path, content_type=content_type)
        content_hash = self.calculate_content_hash(path)
        payload = self.build_reel_payload(part_number, path, title, description, content_hash, content_type=content_type)
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
            "content_type": content_type,
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
            "preflight": {"success": preflight.success, "errors": list(preflight.errors), "details": preflight.details},
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
            preflight={"success": preflight.success, "errors": list(preflight.errors), "details": preflight.details},
            publication_status=status,
            dry_run_payload=payload,
            report_path=str(report_path),
        )

    def _redacted_error(self, body: bytes, status_code: int) -> str:
        payload = {}
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        error = payload.get("error", payload if isinstance(payload, dict) else {})
        message = str(error.get("message", body.decode("utf-8", errors="replace").strip()))
        message = message.replace(self.access_token, "[redacted]")
        redacted_url = urllib.parse.quote(self.access_token, safe="") if self.access_token else ""
        if redacted_url:
            message = message.replace(redacted_url, "[redacted]")
        code = error.get("code")
        error_type = error.get("type")
        trace_id = error.get("fbtrace_id")
        result = [f"Meta Graph API request failed with HTTP {status_code}."]
        if code is not None:
            result.append(f"code={code}")
        if error_type:
            result.append(f"type={error_type}")
        if trace_id:
            result.append(f"trace={trace_id}")
        if message:
            result.append(f"message={message}")
        return " ".join(result)

    def _request_json(self, method: str, url: str, body: Any | None = None, timeout: int | None = None) -> dict[str, Any]:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            raise FacebookApiError(self._redacted_error(raw, exc.code)) from exc
        except urllib.error.URLError as exc:
            raise FacebookApiError(f"Meta Graph API network request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise FacebookApiError(f"Meta Graph API request timed out after {self.timeout_seconds} seconds.") from exc
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FacebookApiError("Meta Graph API returned invalid JSON.") from exc
        return parsed

    def get_page_metadata(self) -> dict[str, Any]:
        if not self.access_token or not self.page_id:
            raise FacebookPublisherError("META_PAGE_ID and META_PAGE_ACCESS_TOKEN are required before contacting Meta.")
        query = urllib.parse.urlencode({
            "fields": "id,name,username,link,category",
            "access_token": self.access_token,
        })
        return self._request_json(
            "GET",
            f"{self.graph_api_base_url}/{self.graph_api_version}/{self.page_id}?{query}",
        )

    def _start_upload(self, title: str, description: str) -> tuple[str, str]:
        result = self._request_json(
            "POST",
            f"{self.graph_api_base_url}/{self.graph_api_version}/{self.page_id}/video_reels",
            {
                "upload_phase": "start",
                "access_token": self.access_token,
            },
            timeout=self.timeout_seconds,
        )
        video_id = result.get("video_id")
        upload_url = result.get("upload_url")
        if not video_id or not upload_url:
            raise FacebookApiError("Meta did not return both video_id and upload_url for this upload session.")
        return str(video_id), str(upload_url)

    def _upload_binary(self, upload_url: str, video_path: Path) -> dict[str, Any]:
        file_size = video_path.stat().st_size
        request = urllib.request.Request(
            upload_url,
            data=video_path.read_bytes(),
            headers={
                "Authorization": f"OAuth {self.access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(self.timeout_seconds, 300)) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            details = self._redacted_error_body(exc.read(), exc.code)
            raise FacebookApiError(details) from exc
        except urllib.error.URLError as exc:
            raise FacebookApiError(f"Meta video upload connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise FacebookApiError("Meta video upload timed out.") from exc
        if not body:
            return {}
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"raw_response": body.decode("utf-8", errors="replace")}
        return parsed if isinstance(parsed, dict) else {}
    _upload_video = _upload_binary

    def _finish_publish(self, video_id: str, title: str, description: str) -> dict[str, Any]:
        result = self._request_json(
            "POST",
            f"{self.graph_api_base_url}/{self.graph_api_version}/{self.page_id}/video_reels",
            {
                "access_token": self.access_token,
                "video_id": video_id,
                "upload_phase": "finish",
                "video_state": "PUBLISHED",
                "title": title,
                "description": description,
            },
            timeout=self.timeout_seconds,
        )
        if not result.get("success"):
            raise FacebookApiError("Meta accepted the upload, but did not report publication success.")
        return result

    def publish_reel(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        publish_manager,
        content_type: str = "reel",
    ) -> dict[str, Any]:
        path = Path(video_path)
        content_type = content_type or "reel"
        preflight = self.validate_video(path, content_type=content_type)
        content_hash = self.calculate_content_hash(path)

        config_errors = self.validate_configuration()
        if not self.publish_enabled or self.dry_run:
            raise FacebookPublisherError("Live Facebook publishing is disabled. Set FACEBOOK_PUBLISH_ENABLED=true and FACEBOOK_PUBLISH_DRY_RUN=false.")
        if publish_manager is None:
            publish_manager = FacebookPublishManager()

        if config_errors or not self.publish_enabled or self.dry_run:
            if config_errors:
                record = {
                    "part_number": part_number,
                    "video_file_name": path.name,
                    "content_hash": content_hash,
                    "title": title,
                    "description": description,
                    "status": "failed" if config_errors else "dry_run",
                    "meta_graph_api_version": self.graph_api_version,
                    "meta_video_id": None,
                    "meta_post_id": None,
                    "upload_phase": "not_started",
                    "errors": list(config_errors) + list(preflight.errors),
                    "created_at": utc_now(),
                    "published_at": None,
                }
                publish_manager.upsert_record(record)
                return {
                    "success": False,
                    "part_number": part_number,
                    "content_hash": content_hash,
                    "errors": list(config_errors) + list(preflight.errors),
                }
            return self.run_dry_run(part_number, path, title, description, publish_manager)

        prior_record = publish_manager.find_record(part_number=part_number, content_hash=content_hash)
        if prior_record is not None and prior_record.get("status") == "published":
            return {
                "success": True,
                "skipped": True,
                "reason": "already_published",
                "part_number": part_number,
                "content_hash": content_hash,
                "meta_video_id": prior_record.get("meta_video_id"),
                "meta_post_id": prior_record.get("meta_post_id"),
                "errors": [],
            }

        if not preflight.success:
            record = {
                "part_number": part_number,
                "video_file_name": path.name,
                "content_hash": content_hash,
                "title": title,
                "description": description,
                "status": "failed",
                "meta_graph_api_version": self.graph_api_version,
                "meta_video_id": None,
                "meta_post_id": None,
                "upload_phase": "not_started",
                "errors": list(preflight.errors),
                "created_at": utc_now(),
                "published_at": None,
            }
            publish_manager.upsert_record(record)
            return {
                "success": False,
                "part_number": part_number,
                "content_hash": content_hash,
                "errors": list(preflight.errors),
            }



        pending_record = {
            "part_number": part_number,
            "video_file_name": path.name,
            "content_hash": content_hash,
            "title": title,
            "description": description,
            "status": "publish_started",
            "meta_graph_api_version": self.graph_api_version,
            "meta_video_id": None,
            "meta_post_id": None,
            "upload_phase": "initialize",
            "errors": [],
            "created_at": utc_now(),
            "published_at": None,
        }
        publish_manager.upsert_record(pending_record)

        video_id = None
        try:
            video_id, upload_url = self._start_upload(title, description)
            publish_manager.upsert_record(
                {
                    "part_number": part_number,
                    "video_file_name": path.name,
                    "content_hash": content_hash,
                    "title": title,
                    "description": description,
                    "status": "uploading",
                    "meta_graph_api_version": self.graph_api_version,
                    "meta_video_id": video_id,
                    "meta_post_id": None,
                    "upload_phase": "transfer",
                    "errors": [],
                    "content_type": content_type,
                    "created_at": pending_record["created_at"],
                }
            )
            self._upload_binary(upload_url, path)
            publish_manager.upsert_record(
                {
                    "part_number": part_number,
                    "video_file_name": path.name,
                    "content_hash": content_hash,
                    "title": title,
                    "description": description,
                    "status": "finish_requested",
                    "meta_graph_api_version": self.graph_api_version,
                    "meta_video_id": video_id,
                    "meta_post_id": None,
                    "upload_phase": "finish",
                    "errors": [],
                    "content_type": content_type,
                    "created_at": pending_record["created_at"],
                }
            )
            finish = self._finish_publish(video_id, title, description)
            post_id = finish.get("post_id") or finish.get("video_id") or ""
            published_record = {
                "part_number": part_number,
                "video_file_name": path.name,
                "content_hash": content_hash,
                "title": title,
                "description": description,
                "status": "published",
                "meta_graph_api_version": self.graph_api_version,
                "meta_video_id": video_id,
                "meta_post_id": post_id,
                "upload_phase": "finish",
                "errors": [],
                "content_type": content_type,
                "created_at": pending_record["created_at"],
                "published_at": utc_now(),
            }
            publish_manager.upsert_record(published_record)
            return {
                "success": True,
                "part_number": part_number,
                "content_hash": content_hash,
                "meta_video_id": video_id,
                "meta_post_id": post_id,
                "errors": [],
                "result": finish,
            }
        except Exception as exc:
            publish_manager.upsert_record(
                {
                    "part_number": part_number,
                    "video_file_name": path.name,
                    "content_hash": content_hash,
                    "title": title,
                    "description": description,
                    "status": "failed",
                    "meta_graph_api_version": self.graph_api_version,
                    "meta_video_id": video_id,
                    "meta_post_id": None,
                    "upload_phase": "failed",
                    "errors": [str(exc)],
                    "content_type": content_type,
                    "created_at": pending_record.get("created_at", utc_now()),
                    "published_at": None,
                }
            )
            raise

    def publish_full_video(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        publish_manager,
        content_type: str = "full_video",
    ) -> dict[str, Any]:
        if content_type != "full_video":
            content_type = "full_video"
        if self.dry_run or not self.publish_enabled:
            return self.run_dry_run(part_number, video_path, title, description, publish_manager, content_type=content_type)
        return {
            "success": False,
            "content_type": content_type,
            "reason": "live_page_video_not_implemented",
            "errors": ["Full Page Video live publishing is intentionally reserved until the exact Page Video upload protocol and test credentials are verified."],
        }

    def publish_full_video(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        publish_manager,
    ) -> dict[str, Any]:
        return self.run_dry_run(part_number, video_path, title, description, publish_manager, content_type="full_video")

    def _request_multipart(
        self,
        url: str,
        fields: dict[str, str],
        file_field: str,
        file_name: str,
        file_data: bytes,
        file_content_type: str = "video/mp4",
    ) -> dict[str, Any]:
        boundary = "----QuizBoundary7MA4YWxkTrZu0gW"
        body = bytearray()
        for key, value in fields.items():
            body += (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'
            f"Content-Type: {file_content_type}\r\n\r\n"
        ).encode("utf-8")
        body += file_data
        body += f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(self.timeout_seconds, 300)) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            raise FacebookApiError(self._redacted_error(raw, exc.code)) from exc
        except urllib.error.URLError as exc:
            raise FacebookApiError(f"Facebook Page Video upload connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise FacebookApiError("Facebook Page Video upload timed out.") from exc
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FacebookApiError("Facebook Page Video upload returned invalid JSON.") from exc
        return parsed if isinstance(parsed, dict) else {}

    def _upload_page_video(self, video_path: Path, title: str, description: str) -> dict[str, Any]:
        url = f"{self.video_upload_base_url}/{self.graph_api_version}/{self.page_id}/videos"
        return self._request_multipart(
            url,
            {
                "access_token": self.access_token,
                "title": title,
                "description": description,
            },
            "source",
            video_path.name,
            video_path.read_bytes(),
        )

    def publish_ten_question_video(
        self,
        part_number: int,
        video_path: Path | str,
        title: str,
        description: str,
        publish_manager,
    ) -> dict[str, Any]:
        content_type = "ten_question_video"
        path = Path(video_path)
        preflight = self.validate_video(path, content_type=content_type)
        content_hash = self.calculate_content_hash(path)
        config_errors = self.validate_configuration()

        if not preflight.success or config_errors:
            record = {
                "part_number": part_number,
                "video_file_name": path.name,
                "content_hash": content_hash,
                "title": title,
                "description": description,
                "status": "failed",
                "meta_graph_api_version": self.graph_api_version,
                "meta_video_id": None,
                "meta_post_id": None,
                "upload_phase": "not_started",
                "errors": list(preflight.errors) + list(config_errors),
                "content_type": content_type,
                "created_at": utc_now(),
                "published_at": None,
            }
            publish_manager.upsert_record(record)
            return {
                "success": False,
                "part_number": part_number,
                "content_hash": content_hash,
                "errors": list(preflight.errors) + list(config_errors),
            }

        if self.dry_run or not self.publish_enabled:
            return self.run_dry_run(part_number, path, title, description, publish_manager, content_type=content_type)

        prior_record = publish_manager.find_record(
            part_number=part_number, content_hash=content_hash, content_type=content_type
        )
        if prior_record is not None and prior_record.get("status") == "published":
            return {
                "success": True,
                "skipped": True,
                "reason": "already_published",
                "part_number": part_number,
                "content_hash": content_hash,
                "meta_video_id": prior_record.get("meta_video_id"),
                "meta_post_id": prior_record.get("meta_post_id"),
                "errors": [],
            }

        pending_record = {
            "part_number": part_number,
            "video_file_name": path.name,
            "content_hash": content_hash,
            "title": title,
            "description": description,
            "status": "publish_started",
            "meta_graph_api_version": self.graph_api_version,
            "meta_video_id": None,
            "meta_post_id": None,
            "upload_phase": "initialize",
            "errors": [],
            "content_type": content_type,
            "created_at": utc_now(),
            "published_at": None,
        }
        publish_manager.upsert_record(pending_record)

        try:
            result = self._upload_page_video(path, title, description)
            video_id = result.get("id") or result.get("video_id")
            if not video_id:
                raise FacebookApiError("Meta did not return a video ID for the 10-question Page Video.")
            published_record = dict(pending_record)
            published_record.update(
                {
                    "status": "published",
                    "meta_video_id": str(video_id),
                    "meta_post_id": result.get("post_id") or str(video_id),
                    "upload_phase": "finish",
                    "published_at": utc_now(),
                    "errors": [],
                }
            )
            publish_manager.upsert_record(published_record)
            return {
                "success": True,
                "part_number": part_number,
                "content_hash": content_hash,
                "meta_video_id": str(video_id),
                "meta_post_id": published_record["meta_post_id"],
                "errors": [],
                "result": result,
            }
        except Exception as exc:
            publish_manager.upsert_record(
                {
                    "part_number": part_number,
                    "video_file_name": path.name,
                    "content_hash": content_hash,
                    "title": title,
                    "description": description,
                    "status": "failed",
                    "meta_graph_api_version": self.graph_api_version,
                    "meta_video_id": None,
                    "meta_post_id": None,
                    "upload_phase": "failed",
                    "errors": [str(exc)],
                    "content_type": content_type,
                    "created_at": pending_record["created_at"],
                    "published_at": None,
                }
            )
            raise

    def from_environment(self):
        return self


def serialize_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

def redact_url_secret(value: str) -> str:
    return "[redacted_url]"


def serialize_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

def redact_url_secret(value: str) -> str:
    return "[redacted_url]"


def serialize_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

