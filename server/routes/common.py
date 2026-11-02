"""라우트들이 같이 쓰는 도우미."""
import copy

from fastapi import HTTPException

from ..config import TASK_KEYS, annotation_config, app_settings, survey_config, tasks_config, topic_info
from ..storage import codes_store, session_store


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
        "tasks": tasks_config(),
        "survey": survey_config(),
        "annotation": annotation_config(),
    }


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
