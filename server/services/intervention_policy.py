"""AI Decision: 이번 턴에 피드백을 보여줄지 결정한다.

1단계 · LLM as a judge (prompts/intervention_decision.txt)
    지금 이 피드백을 보여줄 교육적 필요를 0~100 점으로 매기고, 자기 판단(show: true/false)도 낸다.

2단계 · 적응형 보정 (config/settings.json → intervention)
    최근 window(3) 턴 중 피드백을 보여준 비율(rate)을 목표(target_rate ≈ 2/3)와 비교해
    문턱값 T = base_threshold + gain × (rate − target_rate) 를 만든다 (min~max 로 제한).
      · warmup     이전 턴이 min_history 보다 적음      → LLM 판단 그대로
      · on_target  |rate − target| ≤ tolerance          → LLM 판단 그대로
      · too_many   rate 가 목표보다 높음 (T가 올라감)    → LLM이 보여주자고 하고, 점수 ≥ T 일 때만 보여줌
      · too_few    rate 가 목표보다 낮음 (T가 내려감)    → LLM이 보여주자고 하거나, 점수 ≥ T 이면 보여줌
    고칠 부분이 없으면(no_issue) 판정 없이 보여주지 않는다.

예) window 3, target 2/3, base 50, gain 60
    최근 0/3 노출 → T=10 · 1/3 → T=30 · 2/3 → LLM 판단 그대로 · 3/3 → T=70
"""
import json

from ..config import app_settings, settings
from .llm import chat_json
from .prompt_loader import render


def _cfg() -> dict:
    c = app_settings().get("intervention", {})
    return {
        "window": int(c.get("window", 3)),
        "target_rate": float(c.get("target_rate", 2 / 3)),
        "tolerance": float(c.get("tolerance", 0.17)),
        "min_history": int(c.get("min_history", 2)),
        "base_threshold": float(c.get("base_threshold", 50)),
        "gain": float(c.get("gain", 60)),
        "min_threshold": float(c.get("min_threshold", 10)),
        "max_threshold": float(c.get("max_threshold", 90)),
    }


def _recent(session: dict, turn_id: int, window: int) -> list[dict]:
    prev = [t for t in session.get("turns", []) if t["role"] == "user" and t["id"] < turn_id][-window:]
    out = []
    for t in prev:
        fb = t.get("feedback") or {}
        iv = t.get("intervention") or {}
        out.append({
            "turn_id": t["id"],
            "text": t["text"],
            "has_issue": bool(fb.get("has_issue")),
            "severity": fb.get("severity", 0),
            "score": iv.get("score"),
            "shown": bool(t.get("shown")),
        })
    return out


def _heuristic(fb: dict) -> tuple[int, bool]:
    """MOCK 모드이거나 LLM 호출이 실패했을 때 쓰는 대체 점수."""
    score = min(100, int(fb.get("severity", 0)) * 28 + 6 * len(fb.get("items", [])))
    return score, score >= 50


async def _judge(recent: list[dict], fb: dict) -> dict:
    if settings.mock:
        score, show = _heuristic(fb)
        return {"score": score, "llm_show": show, "llm_reason": "(MOCK) severity-based score", "judge_source": "mock"}
    try:
        prompt = render(
            "intervention_decision.txt",
            recent=json.dumps(recent, ensure_ascii=False, indent=2) if recent else "(none yet)",
            current=json.dumps(fb, ensure_ascii=False, indent=2),
        )
        d = await chat_json([{"role": "user", "content": prompt}], settings.feedback_model, temperature=0.2)
        score = max(0, min(100, int(round(float(d.get("score", 0))))))
        show = d.get("show")
        show = bool(show) if isinstance(show, bool) else score >= 50
        return {"score": score, "llm_show": show, "llm_reason": str(d.get("reason", "")), "judge_source": "llm"}
    except Exception as e:
        score, show = _heuristic(fb)
        return {"score": score, "llm_show": show, "llm_reason": f"judge error: {str(e)[:160]}", "judge_source": "fallback"}


async def decide(session: dict, turn_id: int, fb: dict | None) -> dict:
    c = _cfg()
    recent = _recent(session, turn_id, c["window"])
    n = len(recent)
    shown = sum(r["shown"] for r in recent)
    rate = round(shown / n, 3) if n else None
    base = {"window": c["window"], "recent_n": n, "recent_shown": shown, "recent_rate": rate, "target_rate": c["target_rate"]}

    if not fb or not fb.get("has_issue"):
        return {**base, "show": False, "zone": "no_issue", "rule": "no_issue", "score": 0, "llm_show": False,
                "threshold": None, "overridden": False, "judge_source": None, "llm_reason": "", "reason": "nothing to correct"}

    j = await _judge(recent, fb)
    score, llm_show = j["score"], j["llm_show"]
    threshold = None

    if n < c["min_history"]:
        zone, show = "warmup", llm_show
    else:
        diff = rate - c["target_rate"]
        threshold = round(max(c["min_threshold"], min(c["max_threshold"], c["base_threshold"] + c["gain"] * diff)), 1)
        if abs(diff) <= c["tolerance"]:
            zone, show = "on_target", llm_show
        elif diff > 0:
            zone, show = "too_many", llm_show and score >= threshold
        else:
            zone, show = "too_few", llm_show or score >= threshold

    overridden = show != llm_show
    if overridden:
        reason = f"{zone}: judge said {'show' if llm_show else 'hide'} (score {score}), threshold {threshold} → {'show' if show else 'hide'}"
    else:
        reason = f"{zone}: follow judge ({'show' if show else 'hide'}, score {score})"
    return {**base, **j, "show": show, "zone": zone, "rule": zone, "threshold": threshold, "overridden": overridden, "reason": reason}
