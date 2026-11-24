# -*- coding: utf-8 -*-
"""그라운드워크(Groundwork) · FastAPI 진입점."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv

from .db import backup_db, init_db

# 실행 중인 코드의 버전. 화면의 오류 메시지에 실려, "껐다 켰는지"를 사람이 확인할 수 있게 한다.
# 포터블 꾸러미에서는 같은 파일이 '업데이트_내역.txt' 로 들어간다(_build_portable.ps1) — 둘 다 본다.
# 예전엔 VERSION.txt 만 봐서, 정작 버전이 필요한 행정망 꾸러미에서 늘 '알 수 없음'이 떴다.
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
def _read_version() -> str:
    for name in ("VERSION.txt", "업데이트_내역.txt"):
        try:
            return (_ROOT_DIR / name).read_text(encoding="utf-8-sig").strip().splitlines()[0].strip()
        except Exception:
            continue
    return "알 수 없음"


APP_VERSION = _read_version()
from .routers import projects, outline, resources, review, export, library, requests, dashboard, report, inbox, forms, templates, statements, guidelines, setup, survey

# .env 를 backend 폴더 기준으로 로드(작업 위치와 무관하게 동작 — 포터블 실행 대비)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH if _ENV_PATH.exists() else None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    backup_db()      # 마이그레이션보다 먼저 — 손대기 전 파일이 남아 있어야 한다
    init_db()
    yield


app = FastAPI(title="그라운드워크", version="0.1.0", lifespan=lifespan)

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
app.include_router(forms.router)
app.include_router(templates.router)
app.include_router(statements.router)
app.include_router(guidelines.router)
app.include_router(setup.router)
app.include_router(survey.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


# ── 등록되지 않은 /api 경로 잡기 ──
# 반드시 모든 라우터 '뒤'에 있어야 한다(앞의 라우트가 먼저 매칭된다).
#
# 왜 필요한가: 아래 StaticFiles 가 "/" 에 마운트돼 있어서, 없는 API 경로로 POST 하면
# 정적 파일 서버가 받아 "Method Not Allowed" 를 낸다. 사용자에게는 아무 뜻도 없는 말이다.
# 실제로 새 기능(보고전 뽑기)을 추가한 뒤 서버를 다시 켜지 않아 이 사고가 났다.
# 이 앱은 자동 새로고침이 없으므로(플레인 uvicorn) 갱신 후에는 반드시 재시작해야 한다.
@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
               include_in_schema=False)
def _api_not_found(rest: str):
    raise HTTPException(
        404,
        f"이 기능(/api/{rest})은 지금 실행 중인 프로그램에 없습니다. "
        f"프로그램을 껐다가 다시 켜 주세요. 그래도 같은 메시지가 나오면 새 버전이 아닙니다. "
        f"(실행 중인 버전: {APP_VERSION})",
    )


# 프로덕션: 프런트엔드 빌드(frontend/dist)가 있으면 같은 서버에서 서빙한다.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_ROOT = Path(__file__).resolve().parent.parent.parent
_DIST = _ROOT / "frontend" / "dist"


# 사용설명서(frontend/public/사용설명서.html)는 별도 라우트를 두지 않는다.
# Vite 가 개발 서버에서 그대로 서빙하고 빌드 시 dist 로 복사하므로,
# 개발(5173)과 포터블(8000) 양쪽에서 같은 주소 /사용설명서.html 로 열린다.
# 백엔드에 따로 경로를 두면 개발 서버에서만 빈 화면이 뜬다(실제로 그 사고가 있었다).
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
