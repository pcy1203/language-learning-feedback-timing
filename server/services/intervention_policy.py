"""AI Decision: 피드백 AI가 '지금 피드백이 필요하다'(needs_feedback)고 판단하고 실제로 고친 부분이 있으면 보여준다.
점수(L1 · L2 · 시급성)는 기록만 하고 결정에 쓰지 않는다. 판단 근거(rationale)는 Annotation 에서 함께 보여준다."""


def decide(fb: dict | None) -> dict:
    if not fb:
        return {"show": False, "rule": "needs_feedback", "reason": "피드백 생성 실패"}
    return {
        "show": bool(fb.get("has_issue")),
        "rule": "needs_feedback",
        "needs_feedback": fb.get("needs_feedback"),
        "scores": fb.get("scores"),
        "rationale": fb.get("rationale", ""),
    }
