"""FastAPI 앱: API 라우터 등록 + web/ 정적 파일 서빙."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import WEB_DIR, settings
from .routes import admin, annotation, log, session, survey, tts, turn

app = FastAPI(title="Feedback Timing Study")

for r in (session.router, turn.router, tts.router, annotation.router, survey.router, log.router, admin.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "mock": settings.mock}


# API 라우트 뒤에 마운트해야 /api/* 가 가려지지 않는다
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
