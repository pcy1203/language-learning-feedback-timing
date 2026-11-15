"""AI 발화 음성 파일 (data/audio/{CODE}/{task}_{turn_id}.wav). 재생에도 쓰고, 기록으로도 남긴다."""
import io
import wave
from pathlib import Path

from ..config import DATA_DIR


def audio_path(code: str, task: str, turn_id: int) -> Path:
    return DATA_DIR / "audio" / code / f"{task}_{turn_id}.wav"


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def save(code: str, task: str, turn_id: int, pcm: bytes, sample_rate: int = 24000) -> dict | None:
    if not pcm:
        return None
    path = audio_path(code, task, turn_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pcm_to_wav(pcm, sample_rate))
    return {"file": str(path.relative_to(DATA_DIR)), "seconds": round(len(pcm) / 2 / sample_rate, 2)}
