"""AI Decision: 이번 발화의 피드백을 보여줄지 결정한다.

피드백 AI가 문장마다 매긴 L1·L2 점수 중 하나라도 기준값 N 이상인 문장이 있으면 보여준다
(= feedback_agent 가 계산한 has_issue). 기준값은 config/settings.json → feedback_threshold.
노출 비율을 맞추는 별도의 보정은 하지 않는다.
"""


def decide(fb: dict | None) -> dict:
    if not fb:
        return {"show": False, "rule": "no_feedback", "reason": "feedback not available"}
    th = fb.get("thresholds", {})
    flagged = [s for s in fb.get("sentences", []) if s.get("flagged")]
    return {
        "show": bool(fb.get("has_issue")),
        "rule": "threshold",
        "max_l1": fb.get("max_l1"),
        "max_l2": fb.get("max_l2"),
        "threshold_l1": th.get("L1"),
        "threshold_l2": th.get("L2"),
        "flagged_sentences": [s["index"] for s in flagged],
        "reason": (
            f"{len(flagged)} sentence(s) at or above threshold" if flagged
            else "no sentence at or above threshold"
        ),
    }
