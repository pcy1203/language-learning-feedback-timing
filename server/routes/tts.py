"""AI 발화 음성. 실패하거나 MOCK 모드면 204 → 브라우저 내장 음성으로 대체."""
from fastapi import APIRouter, Response
from pydantic import BaseModel

from ..services import tts_service

router = APIRouter(prefix="/api")


class TtsIn(BaseModel):
    text: str


@router.post("/tts")
async def tts(body: TtsIn):
    try:
        audio = await tts_service.synthesize(body.text[:1200])
    except Exception:
        audio = None
    if not audio:
        return Response(status_code=204)
    return Response(content=audio, media_type="audio/mpeg")
