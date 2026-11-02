"""발화 처리: 대화 AI 응답 + 피드백(백그라운드), 피드백 대기·요청."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import app_settings, topic_info
from ..services import conversation_agent, feedback_jobs
from ..storage import session_store
from ..storage.event_logger import log_event, now_iso
from .common import check_task, get_participant

router = APIRouter(prefix="/api")

Task = Literal["user", "ai", "delayed"]
FALLBACK_REPLY = "Sorry, I didn't quite catch that. Could you tell me a little more?"


class TurnIn(BaseModel):
    code: str
    task: Task
    text: str
    duration_s: float | None = None
    input: Literal["speech", "typed"] = "speech"


@router.post("/turn")
async def post_turn(body: TurnIn):
    text = " ".join(body.text.split())
    if not text:
        raise HTTPException(status_code=400, detail="말한 내용이 비어 있어요.")
    p = get_participant(body.code)
    code, task = p["code"], body.task
    check_task(p, task)
    topic = topic_info(p["topics"][task])

    async with session_store.lock(code, task):
        s = session_store.load_session(code, task)
        if not s:
            raise HTTPException(status_code=404, detail="세션이 없어요.")
        if s.get("ended_at"):
            raise HTTPException(status_code=409, detail="이미 종료된 세션이에요.")
        uid = session_store.next_turn_id(s)
        user_turn = {
            "id": uid, "role": "user", "text": text, "ts": now_iso(),
            "duration_s": round(body.duration_s, 2) if body.duration_s is not None else None,
            "input": body.input, "feedback_status": "pending", "shown": False,
        }
        s["turns"].append(user_turn)
        session_store.save_session(code, task, s)
        history = list(s["turns"])
    log_event(code, "user_utterance", {"turn_id": uid, "text": text, "duration_s": user_turn["duration_s"], "input": body.input}, task=task)

    # 피드백은 뒤에서 만든다 (대화 응답을 늦추지 않도록)
    n = int(app_settings().get("context_turns", 6))
    feedback_jobs.start(code, task, uid, topic, history[-(n + 1):-1], text)

    try:
        reply = await conversation_agent.reply(topic, history)
        if not reply:
            raise ValueError("empty reply")
    except Exception as e:
        log_event(code, "ai_error", {"where": "reply", "turn_id": uid, "error": str(e)[:300]}, task=task)
        reply = FALLBACK_REPLY

    ai_turn = {}

    def apply(sess):
        ai_turn.update({"id": session_store.next_turn_id(sess), "role": "ai", "text": reply, "ts": now_iso()})
        sess["turns"].append(dict(ai_turn))

    await session_store.mutate(code, task, apply)
    log_event(code, "ai_utterance", {"turn_id": ai_turn["id"], "text": reply}, task=task)
    public_user = {k: v for k, v in user_turn.items() if k not in ("feedback", "intervention")}
    return {"user_turn": public_user, "ai_turn": ai_turn}


class FeedbackIn(BaseModel):
    code: str
    task: Task
    turn_id: int


@router.post("/feedback/await")
async def await_feedback(body: FeedbackIn):
    """AI Decision: 피드백 생성 + 개입 결정이 끝날 때까지 기다렸다가 보여줄지 알려준다."""
    p = get_participant(body.code)
    if body.task != "ai":
        raise HTTPException(status_code=400, detail="AI Decision 조건에서만 사용해요.")
    t = await feedback_jobs.wait(p["code"], body.task, body.turn_id)
    if not t:
        raise HTTPException(status_code=404, detail="해당 발화를 찾지 못했어요.")
    shown = bool(t.get("shown"))
    return {"turn_id": body.turn_id, "status": t.get("feedback_status"), "show": shown, "feedback": t.get("feedback") if shown else None}


@router.post("/feedback/request")
async def request_feedback(body: FeedbackIn):
    """User Trigger: 참가자가 '피드백 보기'를 눌렀을 때.

    누른 사실은 피드백이 준비됐는지와 상관없이 턴에 바로 기록한다 (requested, requested_at, request_count).
    피드백이 화면에 실제로 나타나면 shown=True, shown_via='request' 로 기록하고, Annotation 은 이 값으로 나뉜다.
    """
    p = get_participant(body.code)
    code = p["code"]
    if body.task != "user":
        raise HTTPException(status_code=400, detail="User Trigger 조건에서만 사용해요.")

    def mark_requested(s):
        turn = session_store.find_turn(s, body.turn_id)
        if turn:
            turn["requested"] = True
            turn.setdefault("requested_at", now_iso())
            turn["request_count"] = int(turn.get("request_count", 0)) + 1

    await session_store.mutate(code, body.task, mark_requested)
    log_event(code, "feedback_requested", {"turn_id": body.turn_id}, task=body.task)
    t = await feedback_jobs.wait(code, body.task, body.turn_id)
    if not t:
        raise HTTPException(status_code=404, detail="해당 발화를 찾지 못했어요.")
    if t.get("feedback_status") != "ready" or not t.get("feedback"):
        return {"turn_id": body.turn_id, "status": "error", "feedback": None}

    first_time = {}

    def apply(s):
        turn = session_store.find_turn(s, body.turn_id)
        if turn and not turn.get("shown"):
            first_time["yes"] = True
            turn["shown"] = True
            turn["shown_at"] = now_iso()
            turn["shown_via"] = "request"
            turn["mode_when_shown"] = s.get("mode")

    s = await session_store.mutate(code, body.task, apply)
    if first_time:
        log_event(code, "feedback_shown", {"turn_id": body.turn_id, "via": "request", "mode": (s or {}).get("mode")}, task=body.task)
    return {"turn_id": body.turn_id, "status": "ready", "feedback": t["feedback"]}
