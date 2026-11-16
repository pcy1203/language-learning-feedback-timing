"""Delayed: 세션이 끝나면 피드백이 있는 발화를 모아 종합 피드백(패턴 + 규칙 단서 + 총평)을 만든다.
프롬프트: prompts/feedback_delayed_summary.txt"""
import json

from ..config import settings
from . import mock
from .llm import generate_json
from .prompt_loader import render

NO_ISSUE_OVERVIEW = "이번 대화에서는 고칠 부분이 없었어요. 하고 싶은 말을 잘 전달했어요!"


def feedback_turns(session: dict) -> list[dict]:
    return [t for t in session.get("turns", []) if t["role"] == "user" and (t.get("feedback") or {}).get("has_issue")]


async def generate(topic: dict, session: dict) -> dict:
    turns = feedback_turns(session)
    if not turns:
        return {"patterns": [], "overview": NO_ISSUE_OVERVIEW}
    if settings.mock_feedback:
        return mock.summary(turns)
    # 저장된 type 'expression' 을 프롬프트의 용어 'naturalness' 로 맞춰 보낸다
    payload = [{"utterance": t["text"], "revised": t["feedback"]["revised"],
                "items": [{**it, "type": "naturalness" if it["type"] == "expression" else it["type"]} for it in t["feedback"]["items"]]}
               for t in turns]
    prompt = render("feedback_delayed_summary.txt", topic=topic["label"], feedback=json.dumps(payload, ensure_ascii=False, indent=2))
    d = await generate_json(prompt)
    patterns = []
    for p in d.get("patterns", [])[:4]:
        try:
            patterns.append({"label": str(p["label"]), "count": int(p.get("count", 1)), "cue": str(p.get("cue", "")).strip()})
        except (KeyError, TypeError, ValueError):
            continue
    return {"patterns": patterns, "overview": str(d.get("overview", ""))}
