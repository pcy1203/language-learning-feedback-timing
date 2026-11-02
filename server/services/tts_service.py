"""AI 발화를 음성(mp3)으로 만든다. MOCK 모드에서는 None → 브라우저 내장 음성으로 대체."""
import hashlib
from collections import OrderedDict

from ..config import settings
from .llm import client

_cache: "OrderedDict[str, bytes]" = OrderedDict()
_CACHE_MAX = 64


async def synthesize(text: str) -> bytes | None:
    if settings.mock or not text.strip():
        return None
    key = hashlib.sha1(f"{settings.tts_model}|{settings.tts_voice}|{text}".encode()).hexdigest()
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    resp = await client().audio.speech.create(
        model=settings.tts_model, voice=settings.tts_voice, input=text, response_format="mp3"
    )
    data = resp.content
    if not isinstance(data, (bytes, bytearray)):
        data = await resp.aread()
    _cache[key] = bytes(data)
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return _cache[key]
