"""피드백 AI (OpenAI). 조건마다 다른 프롬프트로 발화 하나의 피드백을 만든다.

  user    prompts/feedback_user_trigger.txt  참가자가 '피드백 보기'를 눌렀을 때 (+ 세션 뒤 Annotation용)
  ai      prompts/feedback_ai_decision.txt   매 발화: 지금 피드백이 꼭 필요한지 판단 + 근거(rationale)
  delayed prompts/feedback_delayed_turn.txt  매 발화: 피드백 필요 여부 판단 (종료 후 종합 피드백과 함께 표시)

피드백을 줄지는 AI Decision · Delayed 는 모델의 needs_feedback 으로, User Trigger 는 고친 부분이 있는지로 정한다
(요청한 발화이므로 판단 단계 없이 고칠 게 있으면 고치고, 없으면 원문 그대로 돌려받는다).
점수(L1 의미 미전달 · L2 부자연스러움 · 시급성, 1~10 · 높을수록 피드백이 필요한 쪽)는 기록만 하고 결정에 쓰지 않는다.
has_issue = (피드백 필요) 이고 고친 문장에 실제로 바뀐 부분이 있을 때.
"""
import re

from ..config import settings
from . import mock
from .llm import generate_json
from .prompt_loader import render

PROMPTS = {"user": "feedback_user_trigger.txt", "ai": "feedback_ai_decision.txt", "delayed": "feedback_delayed_turn.txt"}


def format_context(turns: list[dict]) -> str:
    if not turns:
        return "(no previous turns)"
    return "\n".join(f"{'AI' if t['role'] == 'ai' else 'Learner'}: {t['text']}" for t in turns)


def _score(v) -> int | None:
    try:
        return max(1, min(10, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _norm(text: str) -> str:
    """대소문자 · 문장부호 · 띄어쓰기 차이는 '바뀐 것'으로 보지 않는다."""
    return " ".join(re.sub(r"[^\w\s']", " ", (text or "").lower().replace("’", "'")).split())


def _text(v) -> str:
    return str(v or "").strip()


def _items(raw) -> list[dict]:
    out = []
    for it in (raw or [])[:3]:
        if not isinstance(it, dict) or not _text(it.get("revised")):
            continue
        # 프롬프트의 naturalness 는 화면·저장에서 expression('더 나은 표현')으로 쓴다
        kind = _text(it.get("type")).split(" ")[0].lower()
        out.append({
            "type": "meaning" if kind == "meaning" else "expression",
            "category": it.get("category") if it.get("category") in ("vocabulary", "grammar", "pragmatics") else "",
            "original": _text(it.get("original")),
            "revised": _text(it.get("revised")),
            "explanation": _text(it.get("explanation")),
        })
    return out


def normalize(raw: dict, utterance: str, task: str) -> dict:
    """모델의 원 응답을 화면·저장용 피드백으로 정리한다."""
    sc = raw.get("scores") or {}
    revised = _text(raw.get("revised")) or utterance
    changed = _norm(revised) != _norm(utterance)
    needs = changed if task == "user" else bool(raw.get("needs_feedback"))
    has_issue = needs and changed
    fb = {
        "condition": task,
        "prompt": PROMPTS[task],
        "needs_feedback": needs,
        "has_issue": has_issue,
        "revised": revised if has_issue else utterance,
        "items": _items(raw.get("items")) if has_issue else [],
        "intended_meaning": _text(raw.get("intended_ko")),
        "scores": {"l1": _score(sc.get("meaning_breakdown", sc.get("meaning"))), "l2": _score(sc.get("unnaturalness", sc.get("naturalness"))),
                   "urgency": _score(sc.get("urgency"))},
    }
    if task == "ai":
        fb["rationale"] = _text(raw.get("rationale"))
    if task == "user":
        fb["likely_concern"] = _text(raw.get("likely_concern"))
    return fb


async def generate(task: str, topic: dict, context: list[dict], utterance: str) -> dict:
    if settings.mock_feedback:
        raw = mock.feedback_raw(utterance, task)
    else:
        prompt = render(PROMPTS[task], topic=topic["label"], context=format_context(context), utterance=utterance)
        raw = await generate_json(prompt)
    return normalize(raw, utterance, task)
