"""Independent YouTube Shorts publisher foundation (Phase 2.7.1: dry-run only).

Reuses the existing 5-question Facebook Reel MP4. Network helpers are present so
they can be unit-tested with mocked responses, but runtime network uploads are
blocked by ``NETWORK_UPLOADS_ENABLED`` and the CLI never calls them in this phase.
No access token, refresh token or resumable session URL is written to disk.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
VIDEO_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos"

# shortcut: off by default; only the manual 2.7.2 workflow sets YOUTUBE_ALLOW_NETWORK_UPLOAD.
NETWORK_UPLOADS_ENABLED = False
NETWORK_UPLOAD_ENV_FLAG = "YOUTUBE_ALLOW_NETWORK_UPLOAD"
CONTROLLED_PRIVACY_STATUS = "private"
SECRET_ENV_NAMES = (
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN",
    "YOUTUBE_CHANNEL_ID",
)

MIN_CHUNK_BYTES = 256 * 1024
DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024
MAX_DURATION_SECONDS = 180.0  # Shorts-only; the 10-question tracker video has no Shorts cap
SHORTS_CONTENT_TYPE = "youtube_shorts"
TEN_QUESTION_CONTENT_TYPE = "youtube_ten_question_video"
VALID_CONTENT_TYPES = {SHORTS_CONTENT_TYPE, TEN_QUESTION_CONTENT_TYPE}
TEN_QUESTION_TAGS = ["general knowledge", "quiz", "trivia", "education", "10 questions"]
REEL_WIDTH = 1080
REEL_HEIGHT = 1920
REEL_FRAME_RATE = "30/1"
MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 5000
MAX_TAGS_LENGTH = 500
ALLOWED_PRIVACY_STATUSES = ("private", "unlisted")


class YouTubePublisherError(Exception):
    """Raised when YouTube publication preparation cannot proceed."""


class YouTubeConfigurationError(YouTubePublisherError):
    """Raised when credentials or metadata are invalid."""


class YouTubeApiError(YouTubePublisherError):
    """Raised for a failed YouTube API request."""

    def __init__(self, message: str, status_code: int | None = None, reason: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class YouTubeSessionExpiredError(YouTubePublisherError):
    """Raised when a resumable upload session is lost and must not be retried blindly."""


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
    metadata: dict[str, Any]
    privacy_status: str
    existing_record: dict[str, Any] | None
    would_upload: bool
    publication_status: str = "dry_run"
    content_type: str = SHORTS_CONTENT_TYPE


def network_uploads_enabled() -> bool:
    """Default off; an explicit environment flag is the only runtime unlock."""
    if NETWORK_UPLOADS_ENABLED:
        return True
    return os.getenv(NETWORK_UPLOAD_ENV_FLAG, "").strip().lower() in {"1", "true", "yes"}


def check_secret_presence(values: dict[str, str] | None = None) -> list[str]:
    """Return the names of missing secrets; never inspect or return their values."""
    values = values if values is not None else {name: os.getenv(name, "") for name in SECRET_ENV_NAMES}
    return [name for name in SECRET_ENV_NAMES if not str(values.get(name, "")).strip()]


def _http_request(method: str, url: str, *, data=None, headers=None, timeout: int = 30):
    """Return (status, headers, body). Isolated so tests can mock all HTTP."""
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _header(headers: dict[str, str] | None, name: str) -> str:
    if not headers:
        return ""
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def _parse_json(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise YouTubePublisherError("YouTube API returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise YouTubePublisherError("YouTube API returned an unexpected JSON payload.")
    return payload


def _error_message(body: bytes) -> str:
    payload = _parse_json(body) if body else {}
    error = payload.get("error") if isinstance(payload.get("error"), dict) else payload
    message = error.get("message") or error.get("error") or body.decode("utf-8", errors="replace").strip()
    return str(message)


def _run_ffprobe(video_path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise YouTubePublisherError("ffprobe is required for YouTube Shorts preflight validation.")
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate,bit_rate",
                "-show_entries",
                "format=duration",
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
        raise YouTubePublisherError(f"Could not probe video metadata for {video_path}.") from exc
    return _parse_json(result.stdout.encode("utf-8"))


def _frame_rate(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (int, float)):
        return f"{int(value)}/1"
    return str(value)


class YouTubePublisher:
    """Prepares and (in later phases) uploads a Reel as a YouTube Short."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        channel_id: str | None = None,
        dry_run: bool | None = None,
        publish_enabled: bool | None = None,
        privacy_status: str | None = None,
        category_id: str | None = None,
        content_type: str = SHORTS_CONTENT_TYPE,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
        timeout_seconds: int = 30,
        token_endpoint: str = TOKEN_ENDPOINT,
        upload_endpoint: str = VIDEO_UPLOAD_ENDPOINT,
    ) -> None:
        from config import (
            YOUTUBE_CATEGORY_ID,
            YOUTUBE_CHANNEL_ID,
            YOUTUBE_PRIVACY_STATUS,
            YOUTUBE_PUBLISH_DRY_RUN,
            YOUTUBE_PUBLISH_ENABLED,
        )

        self.client_id = client_id if client_id is not None else os.getenv("YOUTUBE_CLIENT_ID", "")
        self.client_secret = client_secret if client_secret is not None else os.getenv("YOUTUBE_CLIENT_SECRET", "")
        self.refresh_token = refresh_token if refresh_token is not None else os.getenv("YOUTUBE_REFRESH_TOKEN", "")
        self.channel_id = channel_id if channel_id is not None else YOUTUBE_CHANNEL_ID
        self.dry_run = dry_run if dry_run is not None else YOUTUBE_PUBLISH_DRY_RUN
        self.publish_enabled = publish_enabled if publish_enabled is not None else YOUTUBE_PUBLISH_ENABLED
        self.privacy_status = str(privacy_status or YOUTUBE_PRIVACY_STATUS).strip().lower()
        self.category_id = str(category_id or YOUTUBE_CATEGORY_ID).strip()
        self.content_type = content_type
        self.chunk_bytes = int(chunk_bytes)
        self.timeout_seconds = int(timeout_seconds)
        self.token_endpoint = token_endpoint
        self.upload_endpoint = upload_endpoint
        self._access_token = ""
        self._session_url = ""

    def _redact(self, value: Any) -> str:
        text = str(value)
        for secret in (self.client_secret, self.refresh_token, self._access_token, self._session_url):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text

    def _require_network_allowed(self) -> None:
        if not network_uploads_enabled():
            raise YouTubePublisherError(
                f"YouTube network uploads are disabled. Set {NETWORK_UPLOAD_ENV_FLAG}=true only in the manual workflow."
            )
        if not self.publish_enabled or self.dry_run:
            raise YouTubePublisherError(
                "YouTube network uploads require YOUTUBE_PUBLISH_ENABLED=true and YOUTUBE_PUBLISH_DRY_RUN=false."
            )
        if self.privacy_status != CONTROLLED_PRIVACY_STATUS:
            raise YouTubePublisherError("Only private YouTube uploads are allowed in this phase.")

    def validate_configuration(self) -> tuple[str, ...]:
        errors = []
        if not self.client_id:
            errors.append("YOUTUBE_CLIENT_ID is not configured.")
        if not self.client_secret:
            errors.append("YOUTUBE_CLIENT_SECRET is not configured.")
        if not self.refresh_token:
            errors.append("YOUTUBE_REFRESH_TOKEN is not configured.")
        if self.privacy_status not in ALLOWED_PRIVACY_STATUSES:
            errors.append("YouTube privacy status must be private or unlisted in this phase.")
        if not self.category_id.isdigit():
            errors.append("YouTube category ID must be numeric.")
        if self.content_type not in VALID_CONTENT_TYPES:
            errors.append("YouTube content type must be youtube_shorts or youtube_ten_question_video.")
        if self.chunk_bytes < MIN_CHUNK_BYTES or self.chunk_bytes % MIN_CHUNK_BYTES:
            errors.append("YouTube upload chunk size must be a multiple of 256 KiB.")
        if self.timeout_seconds <= 0:
            errors.append("YouTube request timeout must be greater than zero.")
        return tuple(errors)

    def validate_video(self, video_path: Path | str) -> VideoPreflightResult:
        path = Path(video_path)
        errors: list[str] = []
        details: dict[str, Any] = {"video_path": str(path)}
        if not path.is_file():
            return VideoPreflightResult(False, (f"Video file does not exist: {path}",), details)
        size = path.stat().st_size
        if size <= 0:
            return VideoPreflightResult(False, (f"Video file is empty: {path}",), details)
        try:
            probe = _run_ffprobe(path)
        except YouTubePublisherError as exc:
            return VideoPreflightResult(False, (str(exc),), details)
        video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
        audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None)
        duration = float(probe.get("format", {}).get("duration", 0) or 0)
        details.update(
            {
                "file_size_bytes": size,
                "video_codec": video.get("codec_name") if video else None,
                "audio_codec": audio.get("codec_name") if audio else None,
                "width": int(video["width"]) if video and "width" in video else None,
                "height": int(video["height"]) if video and "height" in video else None,
                "frame_rate": _frame_rate(video.get("r_frame_rate")) if video else None,
                "audio_channels": int(audio["channels"]) if audio and "channels" in audio else None,
                "audio_sample_rate": int(audio["sample_rate"]) if audio and "sample_rate" in audio else None,
                "audio_bitrate": int(audio["bit_rate"]) if audio and audio.get("bit_rate") else None,
                "duration_seconds": duration,
            }
        )
        width, height = details["width"], details["height"]
        if video is None:
            errors.append("The MP4 must contain a video stream.")
        else:
            if video.get("codec_name") != "h264":
                errors.append(f"Video codec is {video.get('codec_name')!r}; expected 'h264'.")
            if (width, height) != (REEL_WIDTH, REEL_HEIGHT):
                errors.append(f"Resolution is {width}x{height}; expected {REEL_WIDTH}x{REEL_HEIGHT}.")
            elif abs(width / height - 9 / 16) > 0.001:
                errors.append("Aspect ratio is not 9:16.")
            if details["frame_rate"] != REEL_FRAME_RATE:
                errors.append(f"Frame rate is {details['frame_rate']}; expected {REEL_FRAME_RATE}.")
        if audio is None:
            errors.append("The MP4 must contain an audio stream.")
        elif audio.get("codec_name") != "aac":
            errors.append(f"Audio codec is {audio.get('codec_name')!r}; expected 'aac'.")
        if duration <= 0:
            errors.append("Video duration must be greater than zero.")
        elif self.content_type == SHORTS_CONTENT_TYPE and duration > MAX_DURATION_SECONDS:
            errors.append(f"Video duration is {duration:.1f}s; YouTube Shorts allow at most 180s.")
        if self.publish_enabled:
            errors.extend(self.validate_configuration())
        return VideoPreflightResult(not errors, tuple(errors), details)

    def calculate_content_hash(self, video_path: Path | str) -> str:
        from core.youtube_publish_manager import sha256_file

        return sha256_file(video_path)

    def validate_metadata(self, metadata: dict[str, Any]) -> tuple[str, ...]:
        errors = []
        snippet = metadata.get("snippet", {})
        status = metadata.get("status", {})
        if not isinstance(snippet, dict) or not isinstance(status, dict):
            return ("Metadata must contain snippet and status objects.",)
        title = snippet.get("title")
        description = snippet.get("description")
        tags = snippet.get("tags", [])
        if not isinstance(title, str) or not title.strip():
            errors.append("YouTube title is required.")
        elif len(title) > MAX_TITLE_LENGTH:
            errors.append(f"YouTube title exceeds {MAX_TITLE_LENGTH} characters.")
        if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_LENGTH:
            errors.append(f"YouTube description exceeds {MAX_DESCRIPTION_LENGTH} characters.")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            errors.append("YouTube tags must be a list of strings.")
        elif sum(len(tag) for tag in tags) > MAX_TAGS_LENGTH:
            errors.append("YouTube tags exceed the total character limit.")
        if not str(snippet.get("categoryId", "")).isdigit():
            errors.append("YouTube categoryId must be numeric.")
        if status.get("privacyStatus") not in ALLOWED_PRIVACY_STATUSES:
            errors.append("YouTube privacy status must be private or unlisted in this phase.")
        return tuple(errors)

    def build_metadata(
        self,
        part_number: int,
        content_hash: str,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.content_type == TEN_QUESTION_CONTENT_TYPE:
            default_title = f"World General Knowledge Quiz | Part {part_number:03d} | 10 Questions"
            default_description = (
                "Test your general knowledge with this 10-question quiz! Answer all 10 "
                "questions, check your score out of 10, and challenge a friend.\n\n"
                f"Content hash: {content_hash}"
            )
            default_tags = list(TEN_QUESTION_TAGS)
        else:
            default_title = f"World General Knowledge Quiz - Part {part_number} #shorts"
            default_description = (
                f"World General Knowledge Quiz, Part {part_number}. Answer in the comments!\n\n"
                f"Content hash: {content_hash}\n#Shorts #GeneralKnowledge #Trivia"
            )
            default_tags = ["shorts", "general knowledge", "trivia", "quiz"]
        metadata = {
            "snippet": {
                "title": title or default_title,
                "description": description or default_description,
                "tags": tags if tags is not None else default_tags,
                "categoryId": self.category_id,
            },
            "status": {
                "privacyStatus": self.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }
        errors = self.validate_metadata(metadata)
        if errors:
            raise YouTubeConfigurationError("; ".join(errors))
        return metadata

    def refresh_access_token(self) -> dict[str, Any]:
        """Exchange the refresh token for a short-lived access token (no disk writes)."""
        self._require_network_allowed()
        errors = self.validate_configuration()
        if errors:
            raise YouTubeConfigurationError("; ".join(errors))
        body = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        status, headers, raw = _http_request(
            "POST",
            self.token_endpoint,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout_seconds,
        )
        if status >= 400:
            raise YouTubeApiError(
                self._redact(_error_message(raw)), status, _header(headers, "X-Goog-Reason") or None
            )
        payload = _parse_json(raw)
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise YouTubePublisherError("Token response did not include an access token.")
        scope = payload.get("scope")
        if scope and YOUTUBE_UPLOAD_SCOPE not in str(scope).split():
            raise YouTubeConfigurationError("Access token is missing the youtube.upload scope.")
        self._access_token = access_token
        return {"access_token": access_token, "expires_in": payload.get("expires_in"), "scope": scope}

    def _start_resumable_session(self, access_token: str, metadata: dict[str, Any], file_size: int) -> str:
        body = json.dumps(metadata).encode("utf-8")
        separator = "&" if "?" in self.upload_endpoint else "?"
        url = f"{self.upload_endpoint}{separator}uploadType=resumable&part=snippet,status"
        status, headers, raw = _http_request(
            "POST",
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "Content-Length": str(len(body)),
                "X-Upload-Content-Type": "video/*",
                "X-Upload-Content-Length": str(file_size),
            },
            timeout=self.timeout_seconds,
        )
        if status >= 400:
            raise YouTubeApiError(
                self._redact(_error_message(raw)), status, _header(headers, "X-Goog-Reason") or None
            )
        session_url = _header(headers, "Location")
        if not session_url:
            raise YouTubePublisherError("YouTube did not return a resumable upload session URL.")
        self._session_url = session_url
        return session_url

    def _resume_offset(self, headers: dict[str, str], file_size: int) -> int | None:
        range_header = _header(headers, "Range")
        if not range_header:
            return None
        # Range: bytes=0-N means bytes through N were received.
        end = range_header.split("=", 1)[-1].split("-", 1)[-1].strip()
        try:
            return int(end) + 1
        except ValueError:
            return None

    def upload_resumable(
        self,
        session_url: str,
        video_path: Path | str,
        access_token: str,
        *,
        start_offset: int = 0,
        with_channel: bool = False,
    ) -> dict[str, Any]:
        """Upload in bounded chunks. Session URL stays in memory only."""
        path = Path(video_path)
        file_size = path.stat().st_size
        offset = start_offset
        with path.open("rb") as handle:
            handle.seek(offset)
            while offset < file_size:
                chunk = handle.read(self.chunk_bytes)
                if not chunk:
                    break
                end = offset + len(chunk) - 1
                status, headers, raw = _http_request(
                    "PUT",
                    session_url,
                    data=chunk,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "video/*",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{file_size}",
                    },
                    timeout=self.timeout_seconds,
                )
                if status == 308:
                    next_offset = self._resume_offset(headers, file_size)
                    if next_offset is None or next_offset <= offset:
                        raise YouTubePublisherError("Resumable upload made no progress; stop for manual recovery.")
                    offset = next_offset
                    handle.seek(offset)
                    continue
                if status in (200, 201):
                    response = _parse_json(raw)
                    video_id = response.get("id")
                    if not video_id:
                        raise YouTubePublisherError("YouTube upload completed without a video ID.")
                    result = {"youtube_video_id": str(video_id), "upload_status": "uploaded"}
                    if with_channel:
                        snippet = response.get("snippet")
                        result["channel_id"] = str(snippet.get("channelId", "")) if isinstance(snippet, dict) else ""
                    return result
                if status in (404, 410):
                    raise YouTubeSessionExpiredError("Resumable upload session expired or was not found.")
                raise YouTubeApiError(
                    self._redact(_error_message(raw)), status, _header(headers, "X-Goog-Reason") or None
                )
        raise YouTubePublisherError("Resumable upload ended without a completion response.")

    def publish(
        self,
        video_path: Path | str,
        part_number: int,
        *,
        content_hash: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Full resumable upload flow; blocked by the Phase 2.7.1 network gate."""
        self._require_network_allowed()
        path = Path(video_path)
        hash_value = content_hash or self.calculate_content_hash(path)
        metadata = self.build_metadata(part_number, hash_value, title=title, description=description, tags=tags)
        token = access_token or self.refresh_access_token()["access_token"]
        session_url = self._start_resumable_session(token, metadata, path.stat().st_size)
        return self.upload_resumable(session_url, path, token)

    def run_dry_run(
        self,
        part_number: int,
        video_path: Path | str,
        manager=None,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> DryRunReport:
        """Validate and report only. No HTTP request and no history write."""
        path = Path(video_path)
        preflight = self.validate_video(path)
        content_hash = ""
        if path.is_file() and path.stat().st_size:
            content_hash = self.calculate_content_hash(path)
        metadata = (
            self.build_metadata(part_number, content_hash, title=title, description=description, tags=tags)
            if content_hash
            else {}
        )
        existing = None
        if manager is not None and content_hash:
            existing = manager.find(
                part_number=part_number,
                content_hash=content_hash,
                upload_status="uploaded",
                content_type=self.content_type,
            )
        return DryRunReport(
            success=preflight.success,
            part_number=part_number,
            video_path=str(path),
            content_hash=content_hash,
            preflight={"success": preflight.success, "errors": list(preflight.errors), "details": preflight.details},
            metadata=metadata,
            privacy_status=self.privacy_status,
            existing_record=existing,
            would_upload=existing is None,
            content_type=self.content_type,
        )

    def publish_once(self, part_number: int, video_path: Path | str, manager) -> dict[str, Any]:
        """One controlled private upload with duplicate/channel checks and independent history."""
        from core.youtube_publish_manager import utc_now

        self._require_network_allowed()
        errors = list(self.validate_configuration())
        if not self.channel_id:
            errors.append("YOUTUBE_CHANNEL_ID is not configured.")
        if errors:
            raise YouTubeConfigurationError("; ".join(errors))

        path = Path(video_path)
        preflight = self.validate_video(path)
        if not preflight.success:
            raise YouTubePublisherError("Video preflight failed: " + "; ".join(preflight.errors))

        content_hash = self.calculate_content_hash(path)
        previous = manager.find(
            part_number=part_number,
            content_hash=content_hash,
            content_type=self.content_type,
        )
        if previous is not None:
            status = previous.get("upload_status")
            if status == "uploaded":
                return {
                    "success": True, "skipped": True, "needs_reconciliation": False,
                    "part_number": part_number, "status": "uploaded", "reason": "Already uploaded; skipped.",
                    "youtube_video_id": previous.get("youtube_video_id", ""),
                }
            if status == "uploading" or (status == "failed" and previous.get("youtube_video_id")):
                reason = f"Earlier upload has status {status} with a video ID; manual reconciliation required."
                return {
                    "success": False, "skipped": True, "needs_reconciliation": True,
                    "part_number": part_number, "status": status, "reason": reason,
                    "youtube_video_id": previous.get("youtube_video_id", ""),
                }

        if self.content_type == TEN_QUESTION_CONTENT_TYPE:
            publish_title = f"World General Knowledge Quiz | Part {part_number:03d} | 10 Questions"
            publish_description = (
                "Test your general knowledge with this 10-question quiz! Answer all 10 "
                "questions, check your score out of 10, and challenge a friend.\n\n"
                f"Content hash: {content_hash}"
            )
        else:
            publish_title = f"World General Knowledge Quiz | Part {part_number:03d} #Shorts"
            publish_description = (
                "Test your general knowledge with this quick quiz! Answer the questions, "
                "check your knowledge, and challenge yourself. Subscribe for more daily quizzes.\n\n"
                f"Content hash: {content_hash}\n#Shorts #GeneralKnowledge #Quiz"
            )
        metadata = self.build_metadata(
            part_number, content_hash, title=publish_title, description=publish_description
        )
        record = {
            "part_number": part_number,
            "video_file_name": path.name,
            "content_hash": content_hash,
            "content_type": self.content_type,
            "title": metadata["snippet"]["title"],
            "youtube_video_id": "",
            "upload_status": "uploading",
            "privacy_status": self.privacy_status,
            "created_at": utc_now(),
            "published_at": None,
            "errors": [],
        }

        try:
            token = self.refresh_access_token()["access_token"]
            session_url = self._start_resumable_session(token, metadata, path.stat().st_size)
            result = self.upload_resumable(session_url, path, token, with_channel=True)
        except Exception as exc:  # never blindly retry an upload with an uncertain result
            message = self._redact(exc)
            if isinstance(exc, YouTubeSessionExpiredError):
                uncertain = True
            elif isinstance(exc, YouTubeApiError):
                uncertain = exc.status_code in (None, 408, 429) or (exc.status_code or 0) >= 500
            else:
                uncertain = True
            record.update(
                {"upload_status": "uploading" if uncertain else "failed", "errors": [message]}
            )
            manager.record(record)
            return {
                "success": False, "skipped": False, "needs_reconciliation": uncertain,
                "part_number": part_number, "status": record["upload_status"], "reason": message,
                "youtube_video_id": "",
            }

        video_id = result["youtube_video_id"]
        channel_id = result.get("channel_id", "")
        if channel_id != self.channel_id:
            reason = (
                f"Channel verification failed: expected {self.channel_id}, "
                f"got {channel_id or 'unknown'}. Manual reconciliation required."
            )
            record.update(
                {
                    "upload_status": "failed",
                    "youtube_video_id": video_id,
                    "errors": [reason],
                }
            )
            manager.record(record)
            return {
                "success": False, "skipped": False, "needs_reconciliation": True,
                "part_number": part_number, "status": "failed", "reason": reason,
                "youtube_video_id": video_id, "channel_id": channel_id,
            }

        record.update(
            {
                "upload_status": "uploaded",
                "youtube_video_id": video_id,
                "published_at": utc_now(),
                "errors": [],
            }
        )
        manager.record(record)
        return {
            "success": True, "skipped": False, "needs_reconciliation": False,
            "part_number": part_number, "status": "uploaded",
            "youtube_video_id": video_id, "channel_id": channel_id,
        }
