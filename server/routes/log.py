"""브라우저에서 보내는 이벤트 (마이크, 음성 재생, 버튼 클릭 등)."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..storage import codes_store
from ..storage.event_logger import log_event

router = APIRouter(prefix="/api")


class LogIn(BaseModel):
    code: str
    event: str
    task: str | None = None
    data: dict = {}
    client_ts: str | None = None


@router.post("/log")
def client_log(body: LogIn):
    code = body.code.strip().upper()
    if not codes_store.get(code):
        return {"ok": False}
    log_event(code, body.event[:64], body.data, task=body.task, source="client", client_ts=body.client_ts)
    return {"ok": True}
