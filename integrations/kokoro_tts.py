"""KokoroTTS integration using its OpenAI-compatible local HTTP endpoint."""
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from config import (
    KOKORO_BASE_URL,
    KOKORO_MODEL,
    KOKORO_VOICE,
    KOKORO_RESPONSE_FORMAT,
    TTS_SPEED,
    TTS_TIMEOUT_SECONDS,
)

# Kokoro reads badly when sentences run together, so ask for a short pause
# between them.  The server understands [pause:0.25s] tags.
# shortcut: the Reel picks up ~0.75s of extra pauses; drop them there if its
# duration ever approaches Meta's 90 second limit.
SENTENCE_PAUSE_SECONDS = 0.25
SENTENCE_BREAK = re.compile(r"([.!?])\s+")


def with_sentence_pauses(text):
    """Insert a pause tag between sentences so the narration breathes."""
    return SENTENCE_BREAK.sub(rf"\1 [pause:{SENTENCE_PAUSE_SECONDS}s] ", text).strip()


class KokoroTTS:
    def __init__(self, base_url=KOKORO_BASE_URL, model=KOKORO_MODEL, voice=KOKORO_VOICE, response_format=KOKORO_RESPONSE_FORMAT, speed=TTS_SPEED):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.response_format = response_format
        self.speed = speed

    def _valid_audio(self, path):
        path = Path(path)
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            audio_duration(path)
            return True
        except (OSError, ValueError, subprocess.SubprocessError, KeyError, IndexError, TypeError):
            return False

    def synthesize(self, text, output_path):
        output_path = Path(output_path)
        if self._valid_audio(output_path):
            return output_path

        payload = {
            "model": self.model,
            "input": with_sentence_pauses(text),
            "voice": self.voice,
            "response_format": self.response_format,
            "speed": self.speed,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/audio/speech",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(request, timeout=TTS_TIMEOUT_SECONDS) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"KokoroTTS request failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("KokoroTTS server is not reachable. Start it and check KOKORO_BASE_URL.") from exc

        if not data:
            raise RuntimeError("KokoroTTS returned an empty audio response.")

        output_path.write_bytes(data)
        if not self._valid_audio(output_path):
            raise RuntimeError(f"KokoroTTS response did not produce a valid audio file: {output_path}")
        return output_path

    def measure(self, output_path):
        return audio_duration(output_path)


def audio_duration(path):
    """Return media duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe was not found. Install FFmpeg before generating timed audio.")
    path = Path(path)
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
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
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe could not read the audio file: {path}") from exc
    payload = json.loads(result.stdout)
    duration = float(payload["format"]["duration"])
    if duration <= 0:
        raise ValueError(f"Invalid audio duration for {path}.")
    return duration