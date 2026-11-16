"""관리자: 참가자 코드 생성·삭제, 대시보드, 로그 조회, CSV/ZIP 내려받기.

모든 값은 요청 때마다 data/ 폴더의 파일에서 다시 읽는다.
그래서 서버를 껐다 켜도, 브라우저 세션이 초기화돼도 같은 기록이 그대로 보인다.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..auth import require_admin
import asyncio
import time

from ..config import DATA_DIR, TASK_KEYS, settings, tasks_config, topics
from ..services import dashboard, gemini_live, llm, transcription
from ..storage import codes_store, csv_export, session_store
from ..storage.event_logger import log_admin_event, read_events

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

Kind = Literal["turns", "events", "annotations", "survey"]


def _status(code: str) -> dict:
    state = session_store.load_state(code)
    sessions = session_store.all_sessions(code)
    if state.get("finished"):
        return {"key": "done", "label": "완료"}
    if sessions or state.get("task_index", 0) > 0 or state.get("step") not in ("overview", "intro"):
        return {"key": "progress", "label": f"Task {state.get('task_index', 0) + 1} 진행 중"}
    return {"key": "new", "label": "시작 전"}


@router.post("/check-api")
async def check_api():
    """두 API에 아주 짧은 호출을 보내 실제로 연결되는지 확인한다 (키가 없거나 MOCK 이면 호출하지 않음)."""
    async def run(kind: str, fn, enabled: bool, why: str):
        if not enabled:
            return {"kind": kind, "ok": None, "detail": why}
        t0 = time.perf_counter()
        try:
            out = await asyncio.wait_for(fn(), timeout=40)
            return {"kind": kind, "ok": True, "detail": out[:80], "ms": int((time.perf_counter() - t0) * 1000)}
        except Exception as e:
            return {"kind": kind, "ok": False, "detail": f"{type(e).__name__}: {str(e)[:200]}", "ms": int((time.perf_counter() - t0) * 1000)}

    async def stt_ping() -> str:
        # Whisper: 모델 접근 권한만 확인 / 다듬기: 아주 짧은 문장 하나를 다듬어 본다
        if settings.stt_engine == "whisper":
            m = await llm.client().models.retrieve(settings.whisper_model)
            return f"{m.id} 사용 가능"
        r = await transcription.cleanup("i go to the park yesterday", "daily life", "What did you do yesterday?")
        return r["text"]

    a = settings.api_status()
    stt_needed = settings.stt_engine == "whisper" or settings.stt_cleanup
    chat, fb, stt = await asyncio.gather(
        run("chat", gemini_live.ping, not settings.mock_chat, "GEMINI_API_KEY 없음" if not a["chat"]["key"] else "MOCK_LLM=1"),
        run("feedback", llm.ping, not settings.mock_feedback, "OPENAI_API_KEY 없음" if not a["feedback"]["key"] else "MOCK_LLM=1"),
        run("stt", stt_ping, stt_needed and not settings.mock_feedback,
            "브라우저 음성 인식만 사용 (API 호출 없음)" if not stt_needed else ("OPENAI_API_KEY 없음" if not a["feedback"]["key"] else "MOCK_LLM=1")),
    )
    log_admin_event("check_api", {"chat": chat, "feedback": fb, "stt": stt})
    return {"api": a, "chat": chat, "feedback": fb, "stt": stt}


@router.get("/meta")
def meta():
    return {"topics": topics(), "tasks": tasks_config(), "orders": codes_store.VALID_ORDERS, "api": settings.api_status()}


@router.get("/codes")
def list_codes():
    return [{**c, "status": _status(c["code"])} for c in codes_store.list_codes()]


@router.get("/log-index")
def log_index():
    """로그 화면 목록: 등록된 코드 + 코드는 삭제됐지만 data/logs 에 기록이 남아 있는 참가자."""
    out = [{"code": c["code"], "status": _status(c["code"]), "deleted": False} for c in codes_store.list_codes()]
    known = {c["code"] for c in out}
    logs_dir = DATA_DIR / "logs"
    if logs_dir.exists():
        for d in sorted(logs_dir.iterdir()):
            if d.is_dir() and d.name not in known:
                out.append({"code": d.name, "status": {"key": "deleted", "label": "코드 삭제됨"}, "deleted": True})
    return out


@router.get("/dashboard")
def get_dashboard(only_finished: bool = False):
    return dashboard.build(only_finished)


@router.get("/export-dashboard.csv")
def export_dashboard(only_finished: bool = False):
    rows = dashboard.summary_rows(dashboard.build(only_finished))
    text = csv_export._csv(["section", "condition", "metric", "value"], rows)
    return _csv_response(text, f"dashboard_summary{'_finished' if only_finished else ''}.csv")


class CodeIn(BaseModel):
    order: list[str]
    topics: dict[str, str]
    memo: str = ""
    code: str | None = None


@router.post("/codes")
def create_code(body: CodeIn):
    if body.order not in codes_store.VALID_ORDERS:
        raise HTTPException(status_code=400, detail="Task 순서가 올바르지 않아요.")
    valid_topics = {t["id"] for t in topics()}
    if set(body.topics) != set(TASK_KEYS) or not set(body.topics.values()) <= valid_topics:
        raise HTTPException(status_code=400, detail="Task마다 대화 주제를 골라 주세요.")
    try:
        rec = codes_store.create(body.order, body.topics, body.memo, body.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_admin_event("code_created", rec)
    return rec


@router.delete("/codes/{code}")
def delete_code(code: str):
    rec = codes_store.delete(code)
    if not rec:
        raise HTTPException(status_code=404, detail="없는 코드예요.")
    # 로그 폴더(data/logs/{CODE})는 지우지 않는다
    log_admin_event("code_deleted", rec)
    return {"ok": True}


def _stats(sessions: dict[str, dict]) -> dict:
    per_task, all_user = {}, []
    for task, s in sessions.items():
        users = [t for t in s.get("turns", []) if t["role"] == "user"]
        all_user += users
        per_task[task] = {
            "user_turns": len(users),
            "avg_duration_s": round(sum(t.get("duration_s") or 0 for t in users) / len(users), 1) if users else None,
            "feedback_ready": sum(1 for t in users if t.get("feedback_status") == "ready"),
            "feedback_with_issue": sum(1 for t in users if (t.get("feedback") or {}).get("has_issue")),
            "feedback_shown": sum(1 for t in users if t.get("shown")),
            "elapsed_s": s.get("elapsed_s"),
        }
    durations = [t.get("duration_s") for t in all_user if t.get("duration_s")]
    return {
        "user_turns": len(all_user),
        "avg_duration_s": round(sum(durations) / len(durations), 1) if durations else None,
        "feedback_ready": sum(v["feedback_ready"] for v in per_task.values()),
        "feedback_shown": sum(v["feedback_shown"] for v in per_task.values()),
        "per_task": per_task,
    }


@router.get("/participants/{code}")
def participant_detail(code: str):
    code = code.strip().upper()
    p = codes_store.get(code)
    sessions = session_store.all_sessions(code)
    events = read_events(code)
    if not p and not sessions and not events:
        raise HTTPException(status_code=404, detail="없는 코드예요.")
    status = _status(code) if p else {"key": "deleted", "label": "코드 삭제됨 · 기록만 남음"}
    if not p:
        # 코드는 지워졌지만 기록은 남은 경우: 세션 파일에서 순서를 복원한다
        order = sorted(sessions, key=lambda k: sessions[k].get("order_index", 9))
        p = {"code": code, "order": order, "topics": {k: s.get("topic") for k, s in sessions.items()}, "memo": "", "deleted": True}
    return {
        "participant": p,
        "state": session_store.load_state(code),
        "status": status,
        "sessions": sessions,
        "events": events,
        "stats": _stats(sessions),
    }


def _csv_response(text: str, filename: str) -> Response:
    return Response(
        content=("﻿" + text).encode("utf-8"),  # 엑셀에서 한글이 깨지지 않도록 BOM
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/{code}/{kind}.csv")
def export_csv(code: str, kind: Kind, task: Literal["user", "ai", "delayed"] | None = None):
    code = code.strip().upper()
    suffix = f"_{task}" if task else ""
    return _csv_response(csv_export.build_csv(kind, code, task), f"{code}{suffix}_{kind}.csv")


@router.get("/export/{code}.zip")
def export_zip(code: str):
    code = code.strip().upper()
    return Response(
        content=csv_export.build_zip(code),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{code}_logs.zip"'},
    )


@router.get("/export-all/{kind}.csv")
def export_all(kind: Kind):
    return _csv_response(csv_export.build_csv_all(kind), f"all_{kind}.csv")
