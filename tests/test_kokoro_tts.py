"""Tests for the Kokoro TTS client: speaking rate and sentence pauses."""
import json
from pathlib import Path

from integrations import kokoro_tts


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_client_sends_the_speaking_rate_and_sentence_pauses(tmp_path, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(b"fake-mp3-bytes")

    monkeypatch.setattr(kokoro_tts.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(kokoro_tts, "audio_duration", lambda path: 1.5)

    client = kokoro_tts.KokoroTTS(speed=0.92)
    output = tmp_path / "clip.mp3"
    client.synthesize("Question 5, easy. Which river flows through Egypt?", output)

    payload = captured["payload"]
    assert payload["speed"] == 0.92
    assert payload["input"] == "Question 5, easy. [pause:0.25s] Which river flows through Egypt?"
    assert payload["voice"] == kokoro_tts.KOKORO_VOICE
    assert output.exists()


def test_production_narrator_is_af_bella():
    # af_bella ships with the pinned Kokoro-FastAPI v0.9.2 voice pack
    # (api/src/voices/v1_0/af_bella.pt) and is the voice the workflows set.
    assert kokoro_tts.KOKORO_VOICE == "af_bella"


def test_workflows_request_the_production_voice():
    root = Path(__file__).resolve().parents[1]
    for name in ("scheduled-world-quiz-videos.yml", "generate-world-quiz-videos.yml", "facebook-test-reel.yml"):
        workflow = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert 'KOKORO_VOICE: "af_bella"' in workflow, name


def test_single_sentences_get_no_pause_tag():
    assert kokoro_tts.with_sentence_pauses("How did you do?") == "How did you do?"
    assert kokoro_tts.with_sentence_pauses("") == ""
