"""로그인, 진행 상태, 세션 시작·조회·피드백 방식 변경·종료."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fastapi.responses import FileResponse

from ..auth import is_admin_code, issue_admin_token
from ..config import app_settings, settings, topic_info
from ..services import conversation_agent, delayed_summary, feedback_jobs
from ..storage import audio_store, session_store
from ..storage.event_logger import log_admin_event, log_event, now_iso
from .common import ai_turn, check_task, get_participant, get_session_or_404, participant_config, public_participant, strip_hidden

router = APIRouter(prefix="/api")

Task = Literal["user", "ai", "delayed"]
Mode = Literal["simple", "detailed"]


@router.get("/public")
def public_info():
    """로그인 화면 · 관리자 화면에 보여줄 정보 (연구명, API 연결 상태). 키 값은 내보내지 않는다."""
    return {"study_title": app_settings().get("study_title", ""), "mock": settings.mock, "api": settings.api_status()}


@router.get("/audio/{code}/{task}/{turn_id}.wav")
def get_audio(code: str, task: Task, turn_id: int):
    p = get_participant(code)
    path = audio_store.audio_path(p["code"], task, turn_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="음성 파일이 없어요.")
    return FileResponse(path, media_type="audio/wav")


class LoginIn(BaseModel):
    code: str


@router.post("/login")
def login(body: LoginIn):
    code = body.code.strip()
    if is_admin_code(code):
        log_admin_event("admin_login")
        return {"role": "admin", "token": issue_admin_token(), "mock": settings.mock}
    p = get_participant(code)
    state = session_store.load_state(p["code"])
    log_event(p["code"], "login", {"state": state})
    return {"role": "participant", "participant": public_participant(p), "state": state, "config": participant_config()}


class ProgressIn(BaseModel):
    code: str
    task_index: int
    step: str
    finished: bool = False
    modes: dict[str, Mode] = {}


@router.post("/progress")
def progress(body: ProgressIn):
    p = get_participant(body.code)
    state = {
        "task_index": body.task_index,
        "step": body.step,
        "finished": body.finished,
        "modes": body.modes,
        "updated_at": now_iso(),
    }
    session_store.save_state(p["code"], state)
    task = p["order"][body.task_index] if 0 <= body.task_index < len(p["order"]) else None
    log_event(p["code"], "step_enter", {"task_index": body.task_index, "step": body.step, "finished": body.finished}, task=task)
    return state


class StartIn(BaseModel):
    code: str
    task: Task
    mode: Mode = "simple"


@router.post("/session/start")
async def start_session(body: StartIn):
    p = get_participant(body.code)
    code = p["code"]
    check_task(p, body.task)
    async with session_store.lock(code, body.task):
        existing = session_store.load_session(code, body.task)
        if existing:
            log_event(code, "session_resume", {}, task=body.task)
            return strip_hidden(existing)
        topic = topic_info(p["topics"][body.task])
        try:
            first = await conversation_agent.opening(topic)
            if not first["text"]:
                raise ValueError("empty opening")
        except Exception as e:
            log_event(code, "ai_error", {"where": "opening", "error": str(e)[:300]}, task=body.task)
            raise HTTPException(status_code=502, detail="AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요.")
        now = now_iso()
        first_turn = ai_turn(code, body.task, 1, first)
        session = {
            "code": code,
            "task": body.task,
            "order_index": p["order"].index(body.task) + 1,
            "topic": topic["id"],
            "mode": body.mode,
            "mode_history": [{"ts": now, "mode": body.mode}],
            "models": {"chat": settings.chat_model, "feedback": settings.feedback_model,
                       "mock_chat": settings.mock_chat, "mock_feedback": settings.mock_feedback},
            "started_at": now,
            "ended_at": None,
            "turns": [first_turn],
        }
        session_store.save_session(code, body.task, session)
    log_event(code, "session_start", {"mode": body.mode, "topic": topic["id"], "models": session["models"]}, task=body.task)
    log_event(code, "ai_utterance", {"turn_id": 1, "text": first_turn["text"], "audio": first_turn.get("audio")}, task=body.task)
    return session


@router.get("/session/{code}/{task}")
def get_session(code: str, task: Task):
    p = get_participant(code)
    return strip_hidden(get_session_or_404(p["code"], task))


class ModeIn(BaseModel):
    code: str
    task: Task
    mode: Mode


@router.post("/session/mode")
async def set_mode(body: ModeIn):
    p = get_participant(body.code)
    prev = {}

    def apply(s):
        prev["mode"] = s.get("mode")
        s["mode"] = body.mode
        s.setdefault("mode_history", []).append({"ts": now_iso(), "mode": body.mode})

    s = await session_store.mutate(p["code"], body.task, apply)
    if s is None:
        raise HTTPException(status_code=404, detail="세션이 없어요.")
    log_event(p["code"], "mode_toggle", {"from": prev.get("mode"), "to": body.mode}, task=body.task)
    return {"mode": body.mode}


class EndIn(BaseModel):
    code: str
    task: Task
    elapsed_s: float | None = None


@router.post("/session/end")
async def end_session(body: EndIn):
    p = get_participant(body.code)
    code = p["code"]
    s = get_session_or_404(code, body.task)
    if s.get("ended_at"):
        return s
    log_event(code, "session_end", {"elapsed_s": body.elapsed_s}, task=body.task)
    # 아직 만들어지는 중인 피드백을 모두 기다린다
    await feedback_jobs.wait_all(code, body.task)

    summary = None
    if body.task == "delayed":
        s = session_store.load_session(code, body.task) or s
        try:
            summary = await delayed_summary.generate(topic_info(s["topic"]), s)
        except Exception as e:
            log_event(code, "ai_error", {"where": "delayed_summary", "error": str(e)[:300]}, task=body.task)
            summary = {"patterns": [], "overview": "", "error": True}

    def apply(sess):
        now = now_iso()
        sess["ended_at"] = now
        sess["elapsed_s"] = body.elapsed_s
        if summary is not None:
            sess["summary"] = summary
            for t in sess["turns"]:
                if t["role"] == "user" and (t.get("feedback") or {}).get("has_issue"):
                    t["shown"] = True
                    t["shown_at"] = now
                    t["shown_via"] = "summary"
                    t["mode_when_shown"] = sess.get("mode")

    s = await session_store.mutate(code, body.task, apply)
    if summary is not None:
        log_event(code, "delayed_summary_generated", {"summary": summary}, task=body.task)
    return s
