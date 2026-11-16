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
        # 대화 상대 AI: Gemini Live (Live API, 음성으로 답하고 받아쓰기로 글자를 받음)
        self.gemini_api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        self.chat_model = os.getenv("CHAT_MODEL", "gemini-3.8-live").strip()
        self.live_voice = os.getenv("LIVE_VOICE", "").strip()          # 비우면 모델 기본 음성
        self.ai_voice = os.getenv("AI_VOICE", "live").strip().lower()  # live | browser

        # 피드백 · 점수 · Delayed 요약: OpenAI (Responses API)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.feedback_model = os.getenv("FEEDBACK_MODEL", "gpt-5.5").strip()
        self.feedback_reasoning_effort = os.getenv("FEEDBACK_REASONING_EFFORT", "low").strip().lower()

        # 학습자 발화 전사: browser = 브라우저 내장 음성 인식 / whisper = 녹음 파일을 OpenAI Whisper 로 전사
        engine = os.getenv("STT_ENGINE", "browser").strip().lower()
        self.stt_engine = engine if engine in ("browser", "whisper") else "browser"
        self.whisper_model = os.getenv("WHISPER_MODEL", "whisper-1").strip()
        # 브라우저 전사를 쓸 때, 음성 인식이 잘못 받아 적은 부분만 가볍게 다듬을지 (1 = 사용)
        self.stt_cleanup = _flag("STT_CLEANUP")
        self.stt_cleanup_model = os.getenv("STT_CLEANUP_MODEL", "gpt-4o-mini").strip()

        # 키가 없거나 MOCK_LLM=1 이면 해당 부분만 가짜 응답으로 동작
        force_mock = _flag("MOCK_LLM")
        self.mock_chat = force_mock or not self.gemini_api_key
        self.mock_feedback = force_mock or not self.openai_api_key
        self.host = os.getenv("HOST", "127.0.0.1").strip()
        self.port = int(os.getenv("PORT", "8000"))

    @property
    def mock(self) -> bool:
        """둘 중 하나라도 가짜 응답이면 True (화면 표시용)."""
        return self.mock_chat or self.mock_feedback

    def api_status(self) -> dict:
        """화면에 보여줄 API 연결 상태 (키 값 자체는 절대 내보내지 않는다)."""
        return {
            "chat": {"provider": "Gemini", "model": self.chat_model, "key": bool(self.gemini_api_key), "mock": self.mock_chat},
            "feedback": {"provider": "OpenAI", "model": self.feedback_model, "key": bool(self.openai_api_key), "mock": self.mock_feedback},
            "voice": "Gemini Live 음성" if (self.ai_voice == "live" and not self.mock_chat) else "브라우저 내장 음성",
            "stt": {
                "engine": self.stt_engine,
                "label": f"Whisper ({self.whisper_model})" if self.stt_engine == "whisper" else "브라우저 내장 음성 인식",
                "cleanup": self.stt_engine == "browser" and self.stt_cleanup,
                "cleanup_model": self.stt_cleanup_model,
                # Whisper · 다듬기는 OpenAI 키로 호출한다
                "mock": self.mock_feedback and (self.stt_engine == "whisper" or self.stt_cleanup),
            },
        }


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
    conf = load_config("topics.json")
    # legacy_topics: 목록에서 뺀 예전 주제 (이미 만든 코드가 쓰고 있을 수 있어 이름만 남겨 둔다)
    for t in conf["topics"] + conf.get("legacy_topics", []):
        if t["id"] == topic_id:
            return t
    return {"id": topic_id, "label": topic_id, "hint": topic_id}


def tasks_config() -> dict:
    return load_config("tasks.json")


def survey_config() -> dict:
    return load_config("survey.json")


def annotation_config() -> dict:
    return load_config("annotation.json")
