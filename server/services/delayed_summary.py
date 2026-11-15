"""Delayed: 세션이 끝나면 피드백 대상(기준값 이상) 발화의 피드백을 모아 종합 요약(패턴 + 총평)을 만든다."""
import json

from ..config import app_settings, settings
from . import mock
from .llm import generate_json
from .prompt_loader import render

NO_ISSUE_OVERVIEW = "이번 대화에서는 고칠 부분이 거의 없었어요. 하고 싶은 말을 잘 전달했어요!"


def feedback_turns(session: dict) -> list[dict]:
    return [t for t in session.get("turns", []) if t["role"] == "user" and (t.get("feedback") or {}).get("has_issue")]


async def generate(topic: dict, session: dict) -> dict:
    turns = feedback_turns(session)
    if not turns:
        return {"patterns": [], "overview": NO_ISSUE_OVERVIEW}
    if settings.mock_feedback:
        return mock.summary(turns)
    payload = [{"utterance": t["text"], "items": t["feedback"]["items"]} for t in turns]
    prompt = render(
        "delayed_summary.txt",
        topic=topic["label"],
        feedback=json.dumps(payload, ensure_ascii=False, indent=2),
        explanation_language=app_settings().get("feedback_explanation_language", "Korean"),
    )
    d = await generate_json(prompt)
    patterns = []
    for p in d.get("patterns", [])[:4]:
        try:
            patterns.append({"label": str(p["label"]), "count": int(p.get("count", 1))})
        except (KeyError, TypeError, ValueError):
            continue
    return {"patterns": patterns, "overview": str(d.get("overview", ""))}
