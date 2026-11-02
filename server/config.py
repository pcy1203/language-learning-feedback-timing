"""경로, 환경 변수(.env), config/*.json 로딩."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"

TASK_KEYS = ("user", "ai", "delayed")
MODES = ("simple", "detailed")

load_dotenv(ROOT / ".env")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


class Settings:
    def __init__(self) -> None:
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.chat_model = os.getenv("CHAT_MODEL", "gpt-4.1").strip()
        self.feedback_model = os.getenv("FEEDBACK_MODEL", "gpt-4.1").strip()
        self.tts_model = os.getenv("TTS_MODEL", "gpt-4o-mini-tts").strip()
        self.tts_voice = os.getenv("TTS_VOICE", "alloy").strip()
        # 키가 없거나 MOCK_LLM=1 이면 가짜 응답으로 동작
        self.mock = _flag("MOCK_LLM") or not self.openai_api_key
        self.host = os.getenv("HOST", "127.0.0.1").strip()
        self.port = int(os.getenv("PORT", "8000"))


settings = Settings()


def load_config(name: str) -> dict:
    """config/*.json 을 매번 새로 읽는다 (서버 재시작 없이 수정 사항 반영)."""
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def app_settings() -> dict:
    return load_config("settings.json")


def topics() -> list[dict]:
    return load_config("topics.json")["topics"]


def topic_info(topic_id: str) -> dict:
    for t in topics():
        if t["id"] == topic_id:
            return t
    return {"id": topic_id, "label": topic_id, "hint": topic_id}


def tasks_config() -> dict:
    return load_config("tasks.json")


def survey_config() -> dict:
    return load_config("survey.json")


def annotation_config() -> dict:
    return load_config("annotation.json")
