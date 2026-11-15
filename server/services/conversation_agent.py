"""대화 상대 AI (Gemini Live): 첫 인사와 매 턴의 응답을 만든다.

- 시스템 지시: prompts/conversation_system.txt (주제 포함)
- 첫 인사: prompts/conversation_opening.txt 를 첫 'user' 턴으로 보내 시작한다 (참가자에게는 보이지 않음)
- 매 턴: [첫 지시, AI 첫 인사, 참가자, AI, …, 참가자(이번 발화)] 대화 전체를 누적해서 보낸다

반환: {"text": 받아쓰기 글자, "pcm": 음성 bytes 또는 b""}
"""
from ..config import settings
from . import gemini_live, mock
from .prompt_loader import render


def _clean(text: str) -> str:
    return " ".join(text.replace("*", "").split()).strip().strip('"')


def _system(topic: dict) -> str:
    return render("conversation_system.txt", topic=topic["label"], topic_hint=topic["hint"])


def _opening_prompt(topic: dict) -> str:
    return render("conversation_opening.txt", topic=topic["label"], topic_hint=topic["hint"])


async def opening(topic: dict) -> dict:
    if settings.mock_chat:
        return {"text": mock.opening(topic["label"], topic["hint"]), "pcm": b""}
    text, pcm = await gemini_live.respond(_system(topic), [("user", _opening_prompt(topic))])
    return {"text": _clean(text), "pcm": pcm}


async def reply(topic: dict, turns: list[dict]) -> dict:
    if settings.mock_chat:
        return {"text": mock.reply(turns), "pcm": b""}
    history: list[tuple[str, str]] = [("user", _opening_prompt(topic))]
    for t in turns:
        history.append(("model" if t["role"] == "ai" else "user", t["text"]))
    text, pcm = await gemini_live.respond(_system(topic), history)
    return {"text": _clean(text), "pcm": pcm}
