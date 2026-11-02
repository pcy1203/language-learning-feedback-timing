"""참가자 코드 목록 (data/codes.json)."""
import json
import re
import secrets
import threading
from itertools import permutations

from ..config import DATA_DIR, TASK_KEYS
from .event_logger import now_iso

FILE = DATA_DIR / "codes.json"
_lock = threading.Lock()

# 헷갈리는 글자(I, O, 0, 1)는 뺀다
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
VALID_ORDERS = [list(p) for p in permutations(TASK_KEYS)]
CODE_RE = re.compile(r"^[A-Z0-9]{6}$")


def _read() -> dict:
    if not FILE.exists():
        return {}
    with open(FILE, encoding="utf-8") as f:
        return json.load(f)


def _write(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(FILE)


def list_codes() -> list[dict]:
    return sorted(_read().values(), key=lambda c: c.get("created_at", ""), reverse=True)


def get(code: str) -> dict | None:
    return _read().get(code.strip().upper())


def _is_valid_code(code: str) -> bool:
    return bool(CODE_RE.match(code)) and any(c.isdigit() for c in code) and any(c.isalpha() for c in code)


def _new_code(existing: dict) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if _is_valid_code(code) and code not in existing:
            return code


def create(order: list[str], topics: dict[str, str], memo: str = "", code: str | None = None) -> dict:
    with _lock:
        data = _read()
        if code:
            code = code.strip().upper()
            if not _is_valid_code(code):
                raise ValueError("코드는 영문과 숫자를 섞은 6자리여야 해요.")
            if code in data:
                raise ValueError("이미 있는 코드예요.")
        else:
            code = _new_code(data)
        record = {
            "code": code,
            "order": order,
            "topics": topics,
            "memo": memo,
            "created_at": now_iso(),
        }
        data[code] = record
        _write(data)
        return record


def delete(code: str) -> dict | None:
    with _lock:
        data = _read()
        record = data.pop(code.strip().upper(), None)
        _write(data)
        return record
