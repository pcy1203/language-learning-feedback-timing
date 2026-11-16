"""FastAPI 앱: API 라우터 등록 + web/ 정적 파일 서빙."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import WEB_DIR, settings
from .routes import admin, annotation, log, session, survey, turn

app = FastAPI(title="Feedback Timing Study")

for r in (session.router, turn.router, annotation.router, survey.router, log.router, admin.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "mock": settings.mock, "api": settings.api_status()}


@app.middleware("http")
async def no_cache_static(request, call_next):
    """화면 파일(html · js · css)은 매번 새로 받게 한다. 코드를 바꾼 뒤 브라우저에 남은 예전 파일이 섞이지 않도록."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/") and not request.url.path.startswith("/img/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# API 라우트 뒤에 마운트해야 /api/* 가 가려지지 않는다
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
