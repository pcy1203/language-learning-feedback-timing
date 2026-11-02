"""피드백 AI: 매 발화마다 (1) 의미 전달 교정 (2) 더 나은 표현 피드백을 만든다.

간단한 피드백 = revised (고친 문장, 바뀐 부분은 화면에서 강조)
자세한 피드백 = revised + items[].explanation
두 버전 모두 같은 결과에서 나오므로, 세션 중 방식을 바꿔도 이미 나온 피드백이 함께 바뀐다.
"""
from ..config import app_settings, settings
from . import mock
from .llm import chat_json
from .prompt_loader import render


def _format_context(turns: list[dict]) -> str:
    if not turns:
        return "(no previous turns)"
    lines = []
    for t in turns:
        who = "AI" if t["role"] == "ai" else "Learner"
        lines.append(f"{who}: {t['text']}")
    return "\n".join(lines)


def normalize(data: dict, utterance: str) -> dict:
    items = []
    for it in (data.get("items") or [])[:3]:
        if not isinstance(it, dict):
            continue
        kind = it.get("type") if it.get("type") in ("meaning", "expression") else "expression"
        original = str(it.get("original", "")).strip()
        revised = str(it.get("revised", "")).strip()
        if not revised:
            continue
        items.append({"type": kind, "original": original, "revised": revised, "explanation": str(it.get("explanation", "")).strip()})
    try:
        severity = max(0, min(3, int(data.get("severity", 0))))
    except (TypeError, ValueError):
        severity = 0
    has_issue = bool(items) and bool(data.get("has_issue", True))
    if not has_issue:
        items, severity = [], 0
    return {
        "intended_meaning": str(data.get("intended_meaning", "")).strip(),
        "has_issue": has_issue,
        "severity": severity,
        "revised": str(data.get("revised") or utterance).strip(),
        "items": items,
    }


async def generate(topic: dict, context: list[dict], utterance: str) -> dict:
    if settings.mock:
        return mock.feedback(utterance)
    prompt = render(
        "feedback_turn.txt",
        topic=topic["label"],
        context=_format_context(context),
        utterance=utterance,
        explanation_language=app_settings().get("feedback_explanation_language", "Korean"),
    )
    data = await chat_json([{"role": "user", "content": prompt}], settings.feedback_model, temperature=0.2)
    return normalize(data, utterance)
