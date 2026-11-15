"""학습자 녹음 파일 (녹음 버튼 ~ 그만 버튼).

data/recordings/{CODE}/{CODE}_{User_Trigger|AI_Decision|Delayed}_{001}.webm
번호는 그 Task 안에서 학습자가 말한 순서(001, 002, …). 전사가 비어 턴이 되지 못한 녹음은
data/recordings/{CODE}/discarded/ 에 시각을 붙여 따로 남긴다.
"""
from datetime import datetime
from pathlib import Path

from ..config import DATA_DIR

TASK_FILE_LABEL = {"user": "User_Trigger", "ai": "AI_Decision", "delayed": "Delayed"}
_EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
        "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav"}
MEDIA_TYPE = {".webm": "audio/webm", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav"}


def ext_for(mime: str | None) -> str:
    return _EXT.get((mime or "").split(";")[0].strip().lower(), ".webm")


def rec_dir(code: str) -> Path:
    return DATA_DIR / "recordings" / code


def file_name(code: str, task: str, number: int, mime: str | None) -> str:
    return f"{code}_{TASK_FILE_LABEL.get(task, task)}_{number:03d}{ext_for(mime)}"


def save(code: str, task: str, number: int, data: bytes, mime: str | None, seconds: float | None) -> dict | None:
    if not data:
        return None
    path = rec_dir(code) / file_name(code, task, number, mime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"file": path.relative_to(DATA_DIR).as_posix(), "name": path.name, "number": number,
            "bytes": len(data), "mime": (mime or "").split(";")[0] or "audio/webm",
            "seconds": round(seconds, 2) if seconds is not None else None}


def save_discarded(code: str, task: str, data: bytes, mime: str | None) -> str | None:
    if not data:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = rec_dir(code) / "discarded" / f"{code}_{TASK_FILE_LABEL.get(task, task)}_{stamp}{ext_for(mime)}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.relative_to(DATA_DIR).as_posix()


def resolve(rel: str) -> Path | None:
    """세션에 기록된 상대 경로를 실제 파일 경로로 (data 폴더 밖은 막는다)."""
    path = (DATA_DIR / rel).resolve()
    if DATA_DIR.resolve() not in path.parents or not path.is_file():
        return None
    return path
