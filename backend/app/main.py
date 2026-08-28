# -*- coding: utf-8 -*-
"""AI 행정기획 워크벤치 · FastAPI 진입점."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv

from .db import init_db
from .routers import projects, outline, resources, review, export, library, requests, dashboard, report, inbox

# .env 를 backend 폴더 기준으로 로드(작업 위치와 무관하게 동작 — 포터블 실행 대비)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH if _ENV_PATH.exists() else None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI 행정기획 워크벤치", version="0.1.0", lifespan=lifespan)

# 개발 중 Vite(5173)에서 오는 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(outline.router)
app.include_router(resources.router)
app.include_router(review.router)
app.include_router(export.router)
app.include_router(library.router)
app.include_router(requests.router)
app.include_router(dashboard.router)
app.include_router(report.router)
app.include_router(inbox.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 프로덕션: 프런트엔드 빌드(frontend/dist)가 있으면 같은 서버에서 서빙한다.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
