"""라우트들이 같이 쓰는 도우미."""
import copy

from fastapi import HTTPException

from ..config import TASK_KEYS, annotation_config, app_settings, settings, survey_config, tasks_config, thresholds, topic_info
from ..services.gemini_live import SAMPLE_RATE
from ..storage import audio_store, codes_store, session_store
from ..storage.event_logger import now_iso


def get_participant(code: str) -> dict:
    p = codes_store.get(code) if code else None
    if not p:
        raise HTTPException(status_code=404, detail="등록되지 않은 코드예요. 코드를 다시 확인해 주세요.")
    return p


def check_task(participant: dict, task: str) -> None:
    if task not in TASK_KEYS or task not in participant["order"]:
        raise HTTPException(status_code=400, detail="잘못된 Task예요.")


def get_session_or_404(code: str, task: str) -> dict:
    s = session_store.load_session(code, task)
    if not s:
        raise HTTPException(status_code=404, detail="아직 시작하지 않은 세션이에요.")
    return s


def public_participant(p: dict) -> dict:
    return {
        "code": p["code"],
        "order": p["order"],
        "topics": p["topics"],
        "topic_labels": {t: topic_info(p["topics"].get(t, "")).get("label") for t in p["order"]},
    }


def participant_config() -> dict:
    s = app_settings()
    keys = ("session_seconds", "recommended_speech_seconds", "speech_bar_max_seconds", "stt_lang")
    return {
        "study_title": s.get("study_title", ""),
        "settings": {k: s[k] for k in keys if k in s},
        "test_mode_enabled": bool(s.get("test_mode", {}).get("enabled", True)),
        "stt": {"engine": settings.stt_engine, "cleanup": settings.stt_engine == "browser" and settings.stt_cleanup},
        "reply_delay_seconds": {k: v for k, v in (s.get("reply_delay_seconds") or {}).items() if not k.startswith("_")},
        "thresholds": thresholds(),
        "tasks": tasks_config(),
        "survey": survey_config(),
        "annotation": annotation_config(),
    }


def ai_turn(code: str, task: str, turn_id: int, result: dict) -> dict:
    """대화 AI 결과({text, pcm})로 세션에 저장할 AI 턴을 만든다. 음성은 data/audio 에 wav 로 저장."""
    turn = {"id": turn_id, "role": "ai", "text": result["text"], "ts": now_iso()}
    audio = audio_store.save(code, task, turn_id, result.get("pcm") or b"", SAMPLE_RATE)
    if audio:
        turn["audio"] = audio
        if settings.ai_voice == "live":
            turn["audio_url"] = f"/api/audio/{code}/{task}/{turn_id}.wav"
    return turn


def strip_hidden(session: dict) -> dict:
    """세션이 진행 중일 때는 참가자가 아직 보지 않은 피드백을 응답에서 뺀다."""
    if session.get("ended_at"):
        return session
    s = copy.deepcopy(session)
    for t in s.get("turns", []):
        if t.get("role") == "user" and not t.get("shown"):
            t.pop("feedback", None)
            t.pop("intervention", None)
    return s
