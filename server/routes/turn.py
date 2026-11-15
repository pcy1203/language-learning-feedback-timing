"""발화 처리: 녹음 저장 · 전사 · 대화 AI 응답 + 피드백(백그라운드), 피드백 대기·요청, 녹음 재생."""
import asyncio
import time
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import app_settings, settings, topic_info
from ..services import conversation_agent, feedback_jobs, transcription
from ..storage import recording_store, session_store
from ..storage.event_logger import log_event, now_iso
from .common import ai_turn as make_ai_turn
from .common import check_task, get_participant

router = APIRouter(prefix="/api")

Task = Literal["user", "ai", "delayed"]
FALLBACK_REPLY = "Sorry, I didn't quite catch that. Could you tell me a little more?"


def _turn_context(history: list[dict]) -> list[dict]:
    n = int(app_settings().get("context_turns", 6))
    return history[-(n + 1):-1]


async def _transcribe(code: str, task: str, topic: dict, history: list[dict], *, text: str, input_kind: str,
                      audio: bytes, mime: str | None) -> dict:
    """화면·저장·피드백에 쓸 최종 글자를 만든다.

    - 직접 입력: 그대로
    - STT_ENGINE=whisper: 녹음 파일을 Whisper 로 전사 (브라우저 미리보기 글자는 stt_preview 로만 남김)
    - STT_ENGINE=browser + STT_CLEANUP=1: 브라우저 전사에서 잘못 알아들은 단어만 다듬음 (원문은 stt_raw)
    """
    info: dict = {"engine": "typed" if input_kind == "typed" else settings.stt_engine}
    if input_kind == "typed":
        info["text"] = text
        return info
    if settings.stt_engine == "whisper" and audio:
        t0 = time.perf_counter()
        try:
            info["text"] = await transcription.whisper(audio, mime, fallback_text=text)
            info["model"] = settings.whisper_model if not settings.mock_feedback else "mock"
        except Exception as e:
            # Whisper 가 실패하면 브라우저 미리보기 글자로라도 이어간다
            log_event(code, "stt_error", {"where": "whisper", "error": str(e)[:300]}, task=task)
            info["text"], info["fallback"] = text, "browser_preview"
        info["ms"] = int((time.perf_counter() - t0) * 1000)
        info["preview"] = text
        return info
    info["text"] = text
    if settings.stt_cleanup and text:
        t0 = time.perf_counter()
        previous_ai = next((t["text"] for t in reversed(history) if t.get("role") == "ai"), "")
        try:
            r = await transcription.cleanup(text, topic.get("label", ""), previous_ai)
            info.update({"text": r["text"], "raw": text, "cleaned": r["changed"], "cleanup": r})
        except Exception as e:
            log_event(code, "stt_error", {"where": "cleanup", "error": str(e)[:300]}, task=task)
            info.update({"raw": text, "cleaned": False})
        info["ms"] = int((time.perf_counter() - t0) * 1000)
    return info


@router.post("/turn")
async def post_turn(
    code: str = Form(...),
    task: Task = Form(...),
    text: str = Form(""),
    duration_s: float | None = Form(None),
    input: Literal["speech", "typed"] = Form("speech"),
    audio: UploadFile | None = File(None),
):
    """학습자 발화 1개: 녹음 저장 → 전사(옵션) → 턴 저장 → 피드백(백그라운드) + 대화 AI 응답.

    AI Decision 은 피드백 결정이 먼저 끝난 뒤 응답을 돌려줘서, 화면에 피드백이 대화 상대의 말보다 먼저 나온다.
    """
    p = get_participant(code)
    code = p["code"]
    check_task(p, task)
    topic = topic_info(p["topics"][task])
    s = session_store.load_session(code, task)
    if not s:
        raise HTTPException(status_code=404, detail="세션이 없어요.")
    if s.get("ended_at"):
        raise HTTPException(status_code=409, detail="이미 종료된 세션이에요.")

    audio_bytes = await audio.read() if audio is not None else b""
    mime = audio.content_type if audio is not None else None
    text = " ".join(text.split())
    stt = await _transcribe(code, task, topic, s["turns"], text=text, input_kind=input, audio=audio_bytes, mime=mime)
    final = " ".join((stt.get("text") or "").split())
    if not final:
        kept = recording_store.save_discarded(code, task, audio_bytes, mime)
        log_event(code, "utterance_empty", {"duration_s": duration_s, "engine": stt["engine"], "discarded_file": kept}, task=task)
        raise HTTPException(status_code=422, detail="말소리가 인식되지 않았어요. 다시 말해 주세요.")

    async with session_store.lock(code, task):
        s = session_store.load_session(code, task)
        if not s or s.get("ended_at"):
            raise HTTPException(status_code=409, detail="이미 종료된 세션이에요.")
        uid = session_store.next_turn_id(s)
        number = sum(1 for t in s["turns"] if t.get("role") == "user") + 1
        user_turn = {
            "id": uid, "role": "user", "number": number, "text": final, "ts": now_iso(),
            "duration_s": round(duration_s, 2) if duration_s is not None else None,
            "input": input, "stt_engine": stt["engine"], "feedback_status": "pending", "shown": False,
        }
        for key, field in (("raw", "stt_raw"), ("preview", "stt_preview"), ("cleaned", "stt_cleaned"),
                           ("ms", "stt_ms"), ("model", "stt_model"), ("fallback", "stt_fallback")):
            if key in stt:
                user_turn[field] = stt[key]
        rec = recording_store.save(code, task, number, audio_bytes, mime, duration_s)
        if rec:
            user_turn["recording"] = rec
            user_turn["recording_url"] = f"/api/recording/{code}/{task}/{uid}"
        s["turns"].append(user_turn)
        session_store.save_session(code, task, s)
        history = list(s["turns"])
    log_event(code, "user_utterance", {
        "turn_id": uid, "number": number, "text": final, "duration_s": user_turn["duration_s"], "input": input,
        "stt_engine": stt["engine"], "stt_raw": stt.get("raw"), "stt_preview": stt.get("preview"), "stt_cleaned": stt.get("cleaned"),
        "stt_changed_words": (stt.get("cleanup") or {}).get("changed_words"), "stt_ms": stt.get("ms"),
        "recording": (rec or {}).get("file"),
    }, task=task)

    # 피드백(채점)은 뒤에서 만들고, 대화 응답도 동시에 준비한다
    feedback_jobs.start(code, task, uid, topic, _turn_context(history), final)
    reply_job = asyncio.create_task(conversation_agent.reply(topic, history))

    decision = None
    if task == "ai":
        wait_s = float(app_settings().get("ai_decision_feedback_wait_seconds", 60))
        t = await feedback_jobs.wait(code, task, uid, timeout=wait_s)
        if t and t.get("intervention") is not None:
            shown = bool(t.get("shown"))
            decision = {"ready": True, "show": shown, "status": t.get("feedback_status"), "feedback": t.get("feedback") if shown else None}
        else:
            decision = {"ready": False, "show": False, "status": (t or {}).get("feedback_status")}

    try:
        result = await reply_job
        if not result["text"]:
            raise ValueError("empty reply")
    except Exception as e:
        log_event(code, "ai_error", {"where": "reply", "turn_id": uid, "error": str(e)[:300]}, task=task)
        result = {"text": FALLBACK_REPLY, "pcm": b"", "fallback": True}

    ai_turn = {}

    def apply(sess):
        ai_turn.update(make_ai_turn(code, task, session_store.next_turn_id(sess), result))
        if result.get("fallback"):
            ai_turn["fallback"] = True
        sess["turns"].append(dict(ai_turn))

    await session_store.mutate(code, task, apply)
    log_event(code, "ai_utterance", {"turn_id": ai_turn["id"], "text": ai_turn["text"], "audio": ai_turn.get("audio"), "fallback": bool(result.get("fallback"))}, task=task)
    public_user = {k: v for k, v in user_turn.items() if k not in ("feedback", "intervention")}
    return {"user_turn": public_user, "ai_turn": ai_turn, "ai_decision": decision}


@router.get("/recording/{code}/{task}/{turn_id}")
def get_recording(code: str, task: Task, turn_id: int):
    """학습자 녹음 재생 (대화 화면 · Annotation · 관리자 화면)."""
    p = get_participant(code)
    s = session_store.load_session(p["code"], task)
    t = session_store.find_turn(s, turn_id) if s else None
    rel = ((t or {}).get("recording") or {}).get("file")
    path = recording_store.resolve(rel) if rel else None
    if not path:
        raise HTTPException(status_code=404, detail="녹음 파일이 없어요.")
    return FileResponse(path, media_type=recording_store.MEDIA_TYPE.get(path.suffix, "audio/webm"), filename=path.name)


class FeedbackIn(BaseModel):
    code: str
    task: Task
    turn_id: int


@router.post("/feedback/scores")
async def feedback_scores(body: FeedbackIn):
    """테스트 모드(?test=true): 피드백이 만들어질 때까지 기다렸다가 문장별 점수만 돌려준다 (고친 문장은 주지 않음)."""
    if not app_settings().get("test_mode", {}).get("enabled", True):
        raise HTTPException(status_code=403, detail="테스트 모드가 꺼져 있어요.")
    p = get_participant(body.code)
    t = await feedback_jobs.wait(p["code"], body.task, body.turn_id)
    fb = (t or {}).get("feedback")
    if not fb:
        return {"turn_id": body.turn_id, "status": (t or {}).get("feedback_status"), "sentences": []}
    return {
        "turn_id": body.turn_id,
        "status": "ready",
        "thresholds": fb.get("thresholds"),
        "has_issue": fb.get("has_issue"),
        "sentences": [{"index": s["index"], "original": s["original"], "L1": s["l1"]["score"], "L2": s["l2"]["score"],
                       "over": s["over_threshold"], "flagged": s["flagged"]} for s in fb.get("sentences", [])],
    }


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
