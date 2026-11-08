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
FACEBOOK_REELS_QUESTION_COUNT = int(os.getenv("FACEBOOK_REELS_QUESTION_COUNT", "5"))
FACEBOOK_REELS_MIN_QUESTIONS = 3
FACEBOOK_REELS_MAX_QUESTIONS = 5
COUNTDOWN_SECONDS = 5
ANSWER_DISPLAY_SECONDS = 3
TRANSITION_SECONDS = 0.5
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

ENDING_MESSAGE = "How many did you get right? Comment your score below!"
AUDIO_PADDING_SECONDS = 0.5
TTS_TIMEOUT_SECONDS = 180

SFX_TICK_PATH = PROJECT_ROOT / "assets" / "sfx" / "tick.wav"
SFX_TIMEUP_PATH = PROJECT_ROOT / "assets" / "sfx" / "timeup.wav"
SFX_TICK_VOLUME = 0.16
SFX_TIMEUP_VOLUME = 0.22

META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v26.0")
META_GRAPH_API_BASE_URL = os.getenv("META_GRAPH_API_BASE_URL", "https://graph.facebook.com")
META_VIDEO_UPLOAD_BASE_URL = os.getenv("META_VIDEO_UPLOAD_BASE_URL", "https://graph-video.facebook.com")
META_PUBLISH_TIMEOUT_SECONDS = int(os.getenv("META_PUBLISH_TIMEOUT_SECONDS", "120"))
FACEBOOK_REEL_QUESTION_COUNT = int(os.getenv("FACEBOOK_REELS_QUESTION_COUNT", "5"))

FACEBOOK_PUBLISH_ENABLED = (os.getenv("FACEBOOK_PUBLISH_ENABLED", "false").strip().lower() == "true")
FACEBOOK_PUBLISH_DRY_RUN = (os.getenv("FACEBOOK_PUBLISH_DRY_RUN", "true").strip().lower() == "true")
META_PAGE_ID = os.getenv("META_PAGE_ID", "")
META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")

FACEBOOK_REEL_QUESTION_COUNT = int(os.getenv("FACEBOOK_REELS_QUESTION_COUNT", "5"))

# KokoroTTS server defaults. Start a local Kokoro-compatible server first.
KOKORO_BASE_URL = os.getenv("KOKORO_BASE_URL", "http://localhost:7860")
KOKORO_MODEL = os.getenv("KOKORO_MODEL", "kokoro")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_heart")
KOKORO_RESPONSE_FORMAT = os.getenv("KOKORO_RESPONSE_FORMAT", "mp3")
