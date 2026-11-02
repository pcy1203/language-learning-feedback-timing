"""Task(세션)마다 끝날 때 받는 설문."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..storage import session_store
from ..storage.event_logger import log_event, now_iso
from .common import get_participant

router = APIRouter(prefix="/api")


class SurveyIn(BaseModel):
    code: str
    task: Literal["user", "ai", "delayed"]
    likert: dict[str, int]
    text: dict[str, str] = {}


@router.post("/survey")
async def submit_survey(body: SurveyIn):
    p = get_participant(body.code)
    record = {"submitted_at": now_iso(), "likert": body.likert, "text": {k: v.strip() for k, v in body.text.items()}}

    def apply(s):
        s["survey"] = record

    s = await session_store.mutate(p["code"], body.task, apply)
    if s is None:
        raise HTTPException(status_code=404, detail="세션이 없어요.")
    log_event(p["code"], "survey_submit", record, task=body.task)
    return {"ok": True}
