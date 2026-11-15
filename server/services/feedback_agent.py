"""피드백 AI (OpenAI, prompts/feedback_turn.txt): 발화를 문장으로 나누고 문장마다 두 기준을 1~10점으로 채점한다.

  L1 의미 전달 영향 : 청자 직역(literal_ko) ↔ 화자 의도(intended_ko) 비교 + 확인 질문 2개 → 점수
  L2 표현의 자연스러움 : 최소 수정본 ↔ 자연스러움 수정본 비교 → 점수

그다음 이 코드가 기준값 N(config/settings.json → feedback_threshold)을 적용한다.
  · 문장의 L1 ≥ N(L1) 또는 L2 ≥ N(L2) 이고, 고친 문장에 실제로 바뀐 부분이 있으면 → 그 문장은 '피드백 대상'
  · 발화 안에 피드백 대상 문장이 하나라도 있으면 has_issue = True
  · 간단한 피드백(revised) = 피드백 대상 문장만 고친 문장으로 바꾸고 나머지는 원래 문장 그대로 이어 붙인 발화 전체
  · 자세한 피드백 = revised + 피드백 대상 문장의 items(바뀐 부분과 한국어 이유)
세 조건 모두 같은 결과를 쓰고, 조건마다 '언제 보여주느냐'만 다르다.
점수와 상관없이 고친 결과(revised_all, items_all)도 함께 저장한다 (CSV 채점 스크립트·분석용).
"""
import re

from ..config import app_settings, settings, thresholds
from . import mock
from .llm import generate_json
from .prompt_loader import render


def _format_context(turns: list[dict]) -> str:
    if not turns:
        return "(no previous turns)"
    return "\n".join(f"{'AI' if t['role'] == 'ai' else 'Learner'}: {t['text']}" for t in turns)


def _score(v) -> int:
    try:
        return max(1, min(10, int(round(float(v)))))
    except (TypeError, ValueError):
        return 1


def _norm(text: str) -> str:
    """대소문자 · 문장부호 · 띄어쓰기 차이는 '바뀐 것'으로 보지 않는다."""
    return " ".join(re.sub(r"[^\w\s']", " ", (text or "").lower().replace("’", "'")).split())


def _items(raw) -> list[dict]:
    out = []
    for it in (raw or [])[:3]:
        if not isinstance(it, dict):
            continue
        revised = str(it.get("revised", "")).strip()
        if not revised:
            continue
        out.append({
            "type": it.get("type") if it.get("type") in ("meaning", "expression") else "expression",
            "category": it.get("category") if it.get("category") in ("vocabulary", "grammar", "pragmatics") else "",
            "original": str(it.get("original", "")).strip(),
            "revised": revised,
            "explanation": str(it.get("explanation", "")).strip(),
        })
    return out


def apply_thresholds(raw: dict, utterance: str, th: dict | None = None) -> dict:
    """모델의 원 응답(raw)을 정리하고 기준값을 적용해 발화 단위 피드백을 만든다."""
    th = th or thresholds()
    sentences = []
    for i, s in enumerate(raw.get("sentences") or []):
        if not isinstance(s, dict):
            continue
        original = str(s.get("original", "")).strip()
        if not original:
            continue
        l1 = s.get("l1") or {}
        l2 = s.get("l2") or {}
        l1_score, l2_score = _score(l1.get("score")), _score(l2.get("score"))
        revised = str(s.get("revised") or original).strip()
        items = _items(s.get("items"))
        changed = _norm(revised) != _norm(original)
        over = [k for k, sc, n in (("L1", l1_score, th["l1"]), ("L2", l2_score, th["l2"])) if sc >= n]
        sentences.append({
            "index": i + 1,
            "original": original,
            "l1": {
                "score": l1_score,
                "literal_ko": str(l1.get("literal_ko", "")).strip(),
                "other_interpretation": bool(l1.get("other_interpretation")),
                "needs_effort": bool(l1.get("needs_effort")),
                "intended_ko": str(l1.get("intended_ko", "")).strip(),
                "same_meaning": bool(l1.get("same_meaning", True)),
                "reason_ko": str(l1.get("reason_ko", "")).strip(),
            },
            "l2": {
                "score": l2_score,
                "minimal_revision": str(l2.get("minimal_revision", "")).strip(),
                "natural_revision": str(l2.get("natural_revision", "")).strip(),
                "reason_ko": str(l2.get("reason_ko", "")).strip(),
            },
            "revised": revised if changed else original,
            "items": items if changed else [],
            "changed": changed,
            "over_threshold": over,            # 기준을 넘은 항목 (L1, L2)
            "flagged": bool(over) and changed,  # 실제로 피드백으로 보여줄 문장
        })

    if not sentences:  # 모델이 문장을 하나도 돌려주지 않은 경우: 발화 전체를 '문제 없음'으로
        sentences = [{
            "index": 1, "original": utterance,
            "l1": {"score": 1, "literal_ko": "", "other_interpretation": False, "needs_effort": False, "intended_ko": "", "same_meaning": True, "reason_ko": ""},
            "l2": {"score": 1, "minimal_revision": utterance, "natural_revision": utterance, "reason_ko": ""},
            "revised": utterance, "items": [], "changed": False, "over_threshold": [], "flagged": False,
        }]

    flagged = [s for s in sentences if s["flagged"]]
    tag = lambda s: [{**it, "sentence": s["index"]} for it in s["items"]]  # noqa: E731
    return {
        "has_issue": bool(flagged),
        "revised": " ".join(s["revised"] if s["flagged"] else s["original"] for s in sentences),
        "items": [it for s in flagged for it in tag(s)],
        "intended_meaning": " ".join(s["l1"]["intended_ko"] for s in sentences if s["l1"]["intended_ko"]),
        "max_l1": max(s["l1"]["score"] for s in sentences),
        "max_l2": max(s["l2"]["score"] for s in sentences),
        "flagged_sentences": len(flagged),
        "thresholds": {"L1": th["l1"], "L2": th["l2"]},
        # 점수와 상관없이 모든 문장을 고쳤을 때 (분석 · CSV 채점용)
        "revised_all": " ".join(s["revised"] for s in sentences),
        "items_all": [it for s in sentences for it in tag(s)],
        "sentences": sentences,
    }


async def score_raw(topic_label: str, context: list[dict], utterance: str) -> dict:
    """모델에게 채점과 수정을 맡긴 원 응답 (기준값 적용 전)."""
    if settings.mock_feedback:
        return mock.feedback_raw(utterance)
    prompt = render(
        "feedback_turn.txt",
        topic=topic_label,
        context=_format_context(context),
        utterance=utterance,
        explanation_language=app_settings().get("feedback_explanation_language", "Korean"),
    )
    return await generate_json(prompt)


async def generate(topic: dict, context: list[dict], utterance: str) -> dict:
    raw = await score_raw(topic["label"], context, utterance)
    return apply_thresholds(raw, utterance)
