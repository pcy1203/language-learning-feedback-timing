"""학습자 발화 전사 (.env STT_ENGINE / STT_CLEANUP).

- whisper(): 녹음 파일을 OpenAI Whisper 로 전사한다 (STT_ENGINE=whisper).
- cleanup(): 브라우저 음성 인식 결과에서 '잘못 알아들은 단어'만 가볍게 고친다 (STT_CLEANUP=1).
  학습자의 문법·어휘 오류는 고치지 않는다. 고친 결과가 원문과 너무 많이 다르면 원문을 그대로 쓴다.
OpenAI 키가 없으면(MOCK) 실제 호출 없이 원문을 돌려준다.
"""
import difflib
import re

from ..config import PROMPTS_DIR, settings
from . import llm
from .prompt_loader import render


def _whisper_prompt() -> str:
    path = PROMPTS_DIR / "stt_whisper_prompt.txt"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


async def whisper(audio: bytes, mime: str | None, fallback_text: str = "") -> str:
    """녹음 → 글자. MOCK 이면 브라우저 미리보기 글자(fallback_text)를 그대로 쓴다."""
    if settings.mock_feedback:
        return fallback_text or "(mock transcription) I go to the park yesterday and it was very fun."
    ext = {"audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav"}.get((mime or "").split(";")[0], "webm")
    prompt = _whisper_prompt()
    resp = await llm.client().audio.transcriptions.create(
        model=settings.whisper_model,
        file=(f"utterance.{ext}", audio, (mime or "audio/webm").split(";")[0]),
        language="en",
        prompt=prompt or None,
        temperature=0,
    )
    text = " ".join((getattr(resp, "text", "") or "").split())
    # 소리가 거의 없을 때 Whisper 가 예시 문장(prompt)을 그대로 내놓는 경우가 있어 걸러낸다
    if prompt and _words(text) == _words(prompt):
        return ""
    return text


def _too_different(raw: str, fixed: str) -> bool:
    a, b = _words(raw), _words(fixed)
    if not b:
        return True
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return changed > max(3, round(len(a) * 0.3))


async def cleanup(raw: str, topic_label: str, previous_ai: str) -> dict:
    """반환: {text, changed (bool), changed_words, rejected (너무 많이 바뀌어 원문 유지)}"""
    if settings.mock_feedback:
        return {"text": raw, "changed": False, "changed_words": [], "mock": True}
    prompt = render("stt_cleanup.txt", topic=topic_label, previous_ai=previous_ai or "(none)", transcript=raw)
    resp = await llm.client().chat.completions.create(
        model=settings.stt_cleanup_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = llm.parse_json(resp.choices[0].message.content or "{}")
    fixed = " ".join(str(data.get("text") or "").split())
    if _too_different(raw, fixed):
        return {"text": raw, "changed": False, "changed_words": data.get("changed_words") or [], "rejected": True, "suggested": fixed}
    return {"text": fixed, "changed": fixed != raw, "changed_words": data.get("changed_words") or []}
