"""참가자 진행 상태와 Task별 세션 기록.

data/logs/{CODE}/state.json            진행 상태 (몇 번째 Task, 어느 단계)
data/logs/{CODE}/{task}_session.json   대화·피드백·Annotation·설문 전체
"""
import asyncio
import json
import threading
from pathlib import Path
from typing import Callable

from ..config import DATA_DIR, TASK_KEYS

_file_lock = threading.Lock()
_async_locks: dict[tuple[str, str], asyncio.Lock] = {}

DEFAULT_STATE = {"task_index": 0, "step": "intro", "finished": False, "modes": {}}


def participant_dir(code: str) -> Path:
    d = DATA_DIR / "logs" / code
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(path: Path, default):
    if not path.exists():
        return default
    with _file_lock:
        with open(path, encoding="utf-8") as f:
            return json.load(f)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _file_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        tmp.replace(path)


# ---- 진행 상태 ----
def load_state(code: str) -> dict:
    return {**DEFAULT_STATE, **_read(participant_dir(code) / "state.json", {})}


def save_state(code: str, state: dict) -> None:
    _write(participant_dir(code) / "state.json", state)


# ---- 세션 ----
def session_path(code: str, task: str) -> Path:
    return participant_dir(code) / f"{task}_session.json"


def load_session(code: str, task: str) -> dict | None:
    return _read(session_path(code, task), None)


def save_session(code: str, task: str, session: dict) -> None:
    _write(session_path(code, task), session)


def all_sessions(code: str) -> dict[str, dict]:
    out = {}
    for task in TASK_KEYS:
        s = load_session(code, task)
        if s:
            out[task] = s
    return out


def lock(code: str, task: str) -> asyncio.Lock:
    key = (code, task)
    if key not in _async_locks:
        _async_locks[key] = asyncio.Lock()
    return _async_locks[key]


async def mutate(code: str, task: str, fn: Callable[[dict], None]) -> dict | None:
    """세션을 잠근 상태에서 읽고 → 수정하고 → 저장한다."""
    async with lock(code, task):
        s = load_session(code, task)
        if s is None:
            return None
        fn(s)
        save_session(code, task, s)
        return s


def find_turn(session: dict, turn_id: int) -> dict | None:
    for t in session.get("turns", []):
        if t.get("id") == turn_id:
            return t
    return None


def feedback_state(task: str, turn: dict) -> str | None:
    """Annotation 에서 쓰는 발화의 피드백 상태 (web/js/pages/annotation.js 와 같은 규칙).

    seen              고칠 부분이 있었고 피드백을 봤음 (요청 / AI 노출 / 종합 피드백)
    unseen            고칠 부분이 있었지만 대화 중에 보지 않았음
    checked_no_issue  (User Trigger) 피드백을 요청했지만 고칠 부분이 없었음
    no_feedback       고칠 부분이 없어 피드백이 없었음
    None              피드백 생성 실패 / 아직 없음
    """
    if turn.get("role") != "user":
        return None
    fb = turn.get("feedback")
    if not fb:
        return None
    if fb.get("has_issue"):
        return "seen" if turn.get("shown") else "unseen"
    if task == "user" and (turn.get("requested") or turn.get("shown_via") == "request"):
        return "checked_no_issue"
    return "no_feedback"


def next_turn_id(session: dict) -> int:
    return max((t["id"] for t in session.get("turns", [])), default=0) + 1
