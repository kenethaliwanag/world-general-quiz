import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEOS_DIR = OUTPUT_DIR / "videos"

QUESTIONS_FILE = DATA_DIR / "questions.json"
HISTORY_FILE = DATA_DIR / "used_questions.json"

QUIZ_TITLE = "World General Knowledge Quiz"
QUESTIONS_PER_PART = 15
COUNTDOWN_SECONDS = 5
ANSWER_DISPLAY_SECONDS = 3
TRANSITION_SECONDS = 0.5
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

ENDING_MESSAGE = "How many did you get right? Comment your score below!"
AUDIO_PADDING_SECONDS = 0.5
TTS_TIMEOUT_SECONDS = 180

# KokoroTTS server defaults. Start a local Kokoro-compatible server first.
KOKORO_BASE_URL = os.getenv("KOKORO_BASE_URL", "http://localhost:7860")
KOKORO_MODEL = os.getenv("KOKORO_MODEL", "kokoro")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_heart")
KOKORO_RESPONSE_FORMAT = os.getenv("KOKORO_RESPONSE_FORMAT", "mp3")
