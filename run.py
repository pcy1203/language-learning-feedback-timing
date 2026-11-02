"""로컬 실행: python run.py  →  http://127.0.0.1:8000"""
import uvicorn

from server.config import settings

if __name__ == "__main__":
    mode = "MOCK (가짜 응답)" if settings.mock else "OpenAI"
    print(f"\n  ▶ http://{settings.host}:{settings.port}   [{mode}]\n")
    uvicorn.run("server.main:app", host=settings.host, port=settings.port, reload=False)
