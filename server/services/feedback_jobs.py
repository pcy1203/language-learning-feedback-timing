"""피드백 생성을 백그라운드로 돌린다. 조건마다 만드는 시점이 다르다.

- AI Decision: 매 발화 직후. 만들어지면 needs_feedback 으로 바로 보여줄지 결정한다 (대화 상대는 그 뒤에 말한다).
- Delayed:     매 발화 직후. 세션 종료 때 wait_all() 로 모두 기다린 뒤 종합 피드백을 만든다.
- User Trigger: 참가자가 '피드백 보기'를 누른 순간 (purpose=request). 대화는 그동안에도 이어진다.
                세션이 끝나면 요청하지 않은 발화도 Annotation 용으로 만든다 (purpose=annotation, 화면에는 회색).
"""
import asyncio
import time

from ..config import app_settings, topic_info
from ..storage import session_store
from ..storage.event_logger import log_event, now_iso
from . import feedback_agent, intervention_policy

_jobs: dict[tuple[str, str, int], asyncio.Task] = {}


def context_before(session: dict, turn_id: int) -> list[dict]:
    """그 발화 바로 앞의 최근 대화 (config/settings.json → context_turns)."""
    turns = session.get("turns", [])
    idx = next((i for i, t in enumerate(turns) if t["id"] == turn_id), len(turns))
    n = int(app_settings().get("context_turns", 8))
    return turns[max(0, idx - n):idx]


def start(code: str, task: str, turn_id: int, topic: dict, context: list[dict], utterance: str, purpose: str = "live") -> asyncio.Task:
    key = (code, task, turn_id)
    if key in _jobs and not _jobs[key].done():
        return _jobs[key]
    job = asyncio.create_task(_run(code, task, turn_id, topic, context, utterance, purpose))
    _jobs[key] = job
    return job


async def _run(code, task, turn_id, topic, context, utterance, purpose) -> None:
    t0 = time.perf_counter()
    fb, status, error = None, "ready", None
    try:
        fb = await feedback_agent.generate(task, topic, context, utterance)
    except Exception as e:
        status, error = "error", str(e)[:300]
    latency = int((time.perf_counter() - t0) * 1000)

    def apply(s):
        t = session_store.find_turn(s, turn_id)
        if t:
            t["feedback"] = fb
            t["feedback_status"] = status
            t["feedback_latency_ms"] = latency
            t["feedback_purpose"] = purpose

    await session_store.mutate(code, task, apply)
    if fb:
        log_event(code, "feedback_generated", {
            "turn_id": turn_id, "purpose": purpose, "latency_ms": latency, "needs_feedback": fb["needs_feedback"],
            "has_issue": fb["has_issue"], "scores": fb["scores"], "feedback": fb,
        }, task=task)
    else:
        log_event(code, "feedback_error", {"turn_id": turn_id, "purpose": purpose, "latency_ms": latency, "error": error}, task=task)

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
    if (code, task, turn["id"]) in _jobs and not _jobs[(code, task, turn["id"])].done():
        return _jobs[(code, task, turn["id"])]
    log_event(code, "feedback_regenerate", {"turn_id": turn["id"], "previous_status": turn.get("feedback_status")}, task=task)
    purpose = turn.get("feedback_purpose") or ("request" if turn.get("requested") else "live")
    return start(code, task, turn["id"], topic_info(session.get("topic", "")), context_before(session, turn["id"]), turn["text"], purpose)


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


async def request(code: str, task: str, turn_id: int, timeout: float = 120) -> dict | None:
    """User Trigger: 요청한 발화의 피드백을 지금 만든다 (이미 있거나 만드는 중이면 그것을 기다린다)."""
    to_start = {}

    def mark(s):
        t = session_store.find_turn(s, turn_id)
        if t and t.get("role") == "user" and t.get("feedback_status") in (None, "not_requested", "error"):
            t["feedback_status"] = "pending"
            t["feedback_purpose"] = "request"
            to_start["ctx"] = context_before(s, turn_id)
            to_start["text"] = t["text"]
            to_start["topic"] = s.get("topic", "")

    await session_store.mutate(code, task, mark)
    if to_start:
        start(code, task, turn_id, topic_info(to_start["topic"]), to_start["ctx"], to_start["text"], "request")
    return await wait(code, task, turn_id, timeout=timeout)


async def wait_all(code: str, task: str, timeout: float = 150) -> None:
    """세션 종료 전: 진행 중인 피드백을 기다린다.
    User Trigger 는 요청하지 않은 발화의 피드백도 이때 만든다 (Annotation 에서 '보지 않은 피드백'으로 보여줌)."""
    pending: list[tuple[int, list[dict], str]] = []

    def mark(s):
        for t in s.get("turns", []):
            if task == "user" and t.get("role") == "user" and t.get("feedback_status") in (None, "not_requested"):
                t["feedback_status"] = "pending"
                t["feedback_purpose"] = "annotation"
                pending.append((t["id"], context_before(s, t["id"]), t["text"]))

    s = await session_store.mutate(code, task, mark)
    if s:
        topic = topic_info(s.get("topic", ""))
        for turn_id, ctx, text in pending:
            start(code, task, turn_id, topic, ctx, text, "annotation")
        for t in s.get("turns", []):
            if (code, task, t["id"]) not in _jobs:
                _restart_if_lost(code, task, s, t)
    jobs = [j for (c, tk, _), j in _jobs.items() if c == code and tk == task and not j.done()]
    if jobs:
        await asyncio.wait(jobs, timeout=timeout)
