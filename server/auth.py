"""참가 코드 로그인과 관리자 토큰.

관리자는 코드 입력란에 settings.json 의 admin_code(기본 'admin')를 입력해 들어온다.
로그인하면 토큰을 받고, 관리자 API는 이 토큰을 요구한다.
토큰은 data/admin_tokens.json 에 저장되므로 서버를 다시 켜도 로그인이 유지된다 (14일 뒤 만료).
"""
import json
import secrets
import threading
import time

from fastapi import Header, HTTPException, Query

from .config import DATA_DIR, app_settings

TOKENS_FILE = DATA_DIR / "admin_tokens.json"
TTL_SECONDS = 14 * 24 * 3600
_lock = threading.Lock()


def _load() -> dict[str, float]:
    try:
        with open(TOKENS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(tokens: dict[str, float]) -> None:
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKENS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tokens, f)
    tmp.replace(TOKENS_FILE)


def is_admin_code(code: str) -> bool:
    return code.strip().lower() == str(app_settings().get("admin_code", "admin")).lower()


def issue_admin_token() -> str:
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        tokens = {t: exp for t, exp in _load().items() if exp > now}
        tokens[token] = now + TTL_SECONDS
        _save(tokens)
    return token


def require_admin(
    x_admin_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> str:
    # 다운로드 링크(<a href>)는 헤더를 못 붙이므로 ?token= 도 허용
    t = x_admin_token or token
    if not t or _load().get(t, 0) < time.time():
        raise HTTPException(status_code=401, detail="관리자 로그인이 필요해요.")
    return t
