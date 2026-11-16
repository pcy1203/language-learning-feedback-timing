"""Task 종료 후 Annotation 저장."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..storage import session_store
from ..storage.event_logger import log_event, now_iso
from .common import get_participant

router = APIRouter(prefix="/api")


class Answer(BaseModel):
    turn_id: int
    key: str
    value: int
    label: str
    feedback_state: str | None = None
    answered_at: str | None = None


class AnnotationIn(BaseModel):
    code: str
    task: Literal["user", "ai", "delayed"]
    answers: list[Answer]


@router.post("/annotation")
async def save_annotation(body: AnnotationIn):
    p = get_participant(body.code)
    record = {"saved_at": now_iso(), "answers": [a.model_dump() for a in body.answers]}

    def apply(s):
        # 피드백 상태는 서버 기록으로 다시 정해 둔다 (대시보드 집계 기준이 화면 쪽 계산에 의존하지 않도록)
        for a in record["answers"]:
            t = session_store.find_turn(s, a["turn_id"])
            if t:
                a["feedback_state"] = session_store.feedback_state(body.task, t)
        s["annotation"] = record

    s = await session_store.mutate(p["code"], body.task, apply)
    if s is None:
        raise HTTPException(status_code=404, detail="세션이 없어요.")
    log_event(p["code"], "annotation_saved", record, task=body.task)
    return {"ok": True}
