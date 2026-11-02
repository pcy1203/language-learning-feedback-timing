"""모든 이벤트를 data/logs/{CODE}/events.jsonl 에 한 줄씩 기록한다."""
import json
import threading
from datetime import datetime
from pathlib import Path

from ..config import DATA_DIR

_lock = threading.Lock()


def now_iso() -> str:
    """로컬 시간대 포함 ISO 시각 (밀리초)."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def events_path(code: str) -> Path:
    return DATA_DIR / "logs" / code / "events.jsonl"


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def log_event(
    code: str,
    event: str,
    data: dict | None = None,
    task: str | None = None,
    source: str = "server",
    client_ts: str | None = None,
) -> dict:
    record = {"ts": now_iso(), "code": code, "task": task, "event": event, "source": source, "data": data or {}}
    if client_ts:
        record["client_ts"] = client_ts
    _append(events_path(code), record)
    return record


def log_admin_event(event: str, data: dict | None = None) -> None:
    _append(DATA_DIR / "admin_events.jsonl", {"ts": now_iso(), "event": event, "data": data or {}})


def read_events(code: str) -> list[dict]:
    path = events_path(code)
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
