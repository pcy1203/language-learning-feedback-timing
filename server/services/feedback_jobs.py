"""발화마다 피드백 생성(채점)을 백그라운드로 돌린다.

대화 AI의 답변은 피드백을 기다리지 않고 바로 나가고, 피드백은 뒤에서 만들어져 세션에 저장된다.
세 조건 모두 같은 로직으로 미리 만들어 두고, 보여주는 시점만 다르다.
- AI Decision: 피드백이 만들어지면 바로 기준값(N)으로 보여줄지 결정한다.
- User Trigger: 참가자가 '피드백 보기'를 누르면 wait() 로 완성을 기다린다.
- Delayed: 세션 종료 때 wait_all() 로 모두 기다린 뒤 종합 피드백을 만든다.
"""
import asyncio
import time

from ..config import app_settings, topic_info
from ..storage import session_store
from ..storage.event_logger import log_event, now_iso
from . import feedback_agent, intervention_policy

_jobs: dict[tuple[str, str, int], asyncio.Task] = {}


def start(code: str, task: str, turn_id: int, topic: dict, context: list[dict], utterance: str) -> asyncio.Task:
    job = asyncio.create_task(_run(code, task, turn_id, topic, context, utterance))
    _jobs[(code, task, turn_id)] = job
    return job


def _scores_for_log(fb: dict) -> list[dict]:
    return [{"index": s["index"], "L1": s["l1"]["score"], "L2": s["l2"]["score"], "flagged": s["flagged"]} for s in fb.get("sentences", [])]


async def _run(code, task, turn_id, topic, context, utterance) -> None:
    t0 = time.perf_counter()
    fb, status, error = None, "ready", None
    try:
        fb = await feedback_agent.generate(topic, context, utterance)
    except Exception as e:
        status, error = "error", str(e)[:300]
    latency = int((time.perf_counter() - t0) * 1000)

    def apply(s):
        t = session_store.find_turn(s, turn_id)
        if t:
            t["feedback"] = fb
            t["feedback_status"] = status
            t["feedback_latency_ms"] = latency

    await session_store.mutate(code, task, apply)
    if fb:
        log_event(code, "feedback_generated", {
            "turn_id": turn_id, "latency_ms": latency, "has_issue": fb["has_issue"],
            "scores": _scores_for_log(fb), "thresholds": fb["thresholds"], "feedback": fb,
        }, task=task)
    else:
        log_event(code, "feedback_error", {"turn_id": turn_id, "latency_ms": latency, "error": error}, task=task)

    if task != "ai":
        return
    decision = intervention_policy.decide(fb)
    shown_now = {}

    def apply_decision(s):
        t = session_store.find_turn(s, turn_id)
        if not t:
            return
        # 세션이 이미 끝난 뒤 늦게 만들어진 피드백은 참가자가 볼 수 없으므로 '보여줌'으로 기록하지 않는다
        if s.get("ended_at"):
            decision["after_session_end"] = True
        t["intervention"] = decision
        if decision["show"] and not s.get("ended_at"):
            t["shown"] = True
            t["shown_at"] = now_iso()
            t["shown_via"] = "ai"
            t["mode_when_shown"] = s.get("mode")
            shown_now["yes"] = True

    s = await session_store.mutate(code, task, apply_decision)
    log_event(code, "intervention_decision", {"turn_id": turn_id, **decision}, task=task)
    if shown_now:
        log_event(code, "feedback_shown", {"turn_id": turn_id, "via": "ai", "mode": (s or {}).get("mode")}, task=task)


def _restart_if_lost(code: str, task: str, session: dict, turn: dict) -> asyncio.Task | None:
    """서버가 재시작돼 메모리의 작업이 사라졌는데 피드백이 아직 없다면, 파일의 대화 기록으로 다시 만든다."""
    if turn.get("role") != "user" or turn.get("feedback_status") not in ("pending", "error"):
        return None
    if (code, task, turn["id"]) in _jobs:
        return _jobs[(code, task, turn["id"])]
    idx = session["turns"].index(turn)
    n = int(app_settings().get("context_turns", 6))
    context = session["turns"][max(0, idx - n):idx]
    log_event(code, "feedback_regenerate", {"turn_id": turn["id"], "previous_status": turn.get("feedback_status")}, task=task)
    return start(code, task, turn["id"], topic_info(session.get("topic", "")), context, turn["text"])


async def wait(code: str, task: str, turn_id: int, timeout: float = 120) -> dict | None:
    job = _jobs.get((code, task, turn_id))
    if job is None:
        s = session_store.load_session(code, task)
        t = session_store.find_turn(s, turn_id) if s else None
        if t:
            job = _restart_if_lost(code, task, s, t)
    if job is not None:
        try:
            await asyncio.wait_for(asyncio.shield(job), timeout=timeout)
        except Exception:
            pass
    s = session_store.load_session(code, task)
    return session_store.find_turn(s, turn_id) if s else None


async def wait_all(code: str, task: str, timeout: float = 150) -> None:
    """세션 종료 전: 진행 중인 피드백을 기다리고, 서버 재시작 등으로 빠진 피드백은 다시 만든다."""
    s = session_store.load_session(code, task)
    if s:
        for t in s.get("turns", []):
            if (code, task, t["id"]) not in _jobs:
                _restart_if_lost(code, task, s, t)
    jobs = [j for (c, tk, _), j in _jobs.items() if c == code and tk == task and not j.done()]
    if jobs:
        await asyncio.wait(jobs, timeout=timeout)
