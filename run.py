"""로컬 실행: python run.py  →  http://127.0.0.1:8000"""
import sys

import uvicorn

from server.config import settings

if __name__ == "__main__":
    # Windows 콘솔(cp949)에서 출력할 수 없는 문자가 있어도 멈추지 않게
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    a = settings.api_status()
    line = lambda name, s: f"  {name:<10} {s['model']:<18} " + ("MOCK (가짜 응답) - 키 없음" if not s["key"] else ("MOCK (MOCK_LLM=1)" if s["mock"] else "API 키 연결됨"))  # noqa: E731
    print(f"\n  > http://{settings.host}:{settings.port}\n")
    print(line("대화 AI", a["chat"]))
    print(line("피드백", a["feedback"]))
    print(f"  {'AI 음성':<9} {a['voice']}")
    stt = a["stt"]
    print(f"  {'전사':<10} {stt['label']}" + (f" + 다듬기({stt['cleanup_model']})" if stt["cleanup"] else "") + (" (MOCK)" if stt["mock"] else "") + "\n")
    uvicorn.run("server.main:app", host=settings.host, port=settings.port, reload=False)
