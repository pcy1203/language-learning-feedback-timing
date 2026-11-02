"""발화마다 피드백 생성을 백그라운드로 돌린다.

대화 AI의 답변은 피드백을 기다리지 않고 바로 나가고, 피드백은 뒤에서 만들어져 세션에 저장된다.
- AI Decision: 피드백이 만들어지면 이어서 개입 여부를 결정한다 (이전 턴의 결정이 끝난 뒤 순서대로).
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
_last_job: dict[tuple[str, str], asyncio.Task] = {}


def start(code: str, task: str, turn_id: int, topic: dict, context: list[dict], utterance: str) -> asyncio.Task:
    prev = _last_job.get((code, task))
    job = asyncio.create_task(_run(code, task, turn_id, topic, context, utterance, prev))
    _jobs[(code, task, turn_id)] = job
    _last_job[(code, task)] = job
    return job


async def _run(code, task, turn_id, topic, context, utterance, prev) -> None:
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
        log_event(code, "feedback_generated", {"turn_id": turn_id, "latency_ms": latency, "feedback": fb}, task=task)
    else:
        log_event(code, "feedback_error", {"turn_id": turn_id, "latency_ms": latency, "error": error}, task=task)

    if task != "ai":
        return
    # 앞 턴의 개입 결정이 끝나야 '최근 3턴 중 몇 번 보여줬는지'를 정확히 셀 수 있다
    if prev is not None:
        try:
            await prev
        except Exception:
            pass
    session = session_store.load_session(code, task) or {}
    decision = await intervention_policy.decide(session, turn_id, fb)

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


async def wait(code: str, task: str, turn_id: int, timeout: float = 90) -> dict | None:
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


async def wait_all(code: str, task: str, timeout: float = 120) -> None:
    """세션 종료 전: 진행 중인 피드백을 기다리고, 서버 재시작 등으로 빠진 피드백은 다시 만든다."""
    s = session_store.load_session(code, task)
    if s:
        for t in s.get("turns", []):
            if (code, task, t["id"]) not in _jobs:
                _restart_if_lost(code, task, s, t)
    jobs = [j for (c, tk, _), j in _jobs.items() if c == code and tk == task and not j.done()]
    if jobs:
        await asyncio.wait(jobs, timeout=timeout)
