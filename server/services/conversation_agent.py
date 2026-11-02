"""대화 파트너 AI: 첫 인사와 다음 응답을 만든다. 대화 기록은 누적해서 전달한다."""
from ..config import settings
from . import mock
from .llm import chat
from .prompt_loader import render


def _clean(text: str) -> str:
    return " ".join(text.replace("*", "").split()).strip().strip('"')


def _system(topic: dict) -> dict:
    return {"role": "system", "content": render("conversation_system.txt", topic=topic["label"], topic_hint=topic["hint"])}


async def opening(topic: dict) -> str:
    if settings.mock:
        return mock.opening(topic["label"], topic["hint"])
    user = render("conversation_opening.txt", topic=topic["label"], topic_hint=topic["hint"])
    text = await chat([_system(topic), {"role": "user", "content": user}], settings.chat_model, temperature=0.8)
    return _clean(text)


async def reply(topic: dict, turns: list[dict]) -> str:
    if settings.mock:
        return mock.reply(turns)
    messages = [_system(topic)]
    for t in turns:
        role = "assistant" if t["role"] == "ai" else "user"
        messages.append({"role": role, "content": t["text"]})
    text = await chat(messages, settings.chat_model, temperature=0.8)
    return _clean(text)
