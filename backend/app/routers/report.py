# -*- coding: utf-8 -*-
import io
import json
import urllib.parse
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from ..db import connect, now
from ..services.progress import fact_lines
from .dashboard import compute_metrics

router = APIRouter(prefix="/api", tags=["report"])

STATUS_CHOICES = ["정상 추진", "지연 우려", "협의·대기", "보류"]


# ────────────── 설정: 내 이름(작성자) ──────────────
def _get_setting(c, key, default=""):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


class SettingsIn(BaseModel):
    author_name: str | None = None
    author_dept: str | None = None      # 보고전 머리글에 들어가는 부서명


@router.get("/settings")
def get_settings():
    with connect() as c:
        return {"author_name": _get_setting(c, "author_name", ""),
                "author_dept": _get_setting(c, "author_dept", "")}


@router.put("/settings")
def put_settings(s: SettingsIn):
    with connect() as c:
        for key, val in (("author_name", s.author_name), ("author_dept", s.author_dept)):
            if val is not None:
                c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, val.strip()))
        return {"author_name": _get_setting(c, "author_name", ""),
                "author_dept": _get_setting(c, "author_dept", "")}


# ────────────── 진행상황 보고 ──────────────
@router.get("/projects/{pid}/report/preview")
def report_preview(pid: int):
    """보고 팝업에 채워질 '자동 집계 사실'과 작성자 이름을 돌려준다(읽기 전용)."""
    with connect() as c:
        p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        m = compute_metrics(c, p)
        author = _get_setting(c, "author_name", "")
    return {
        "author": author,
        "generated_at": now(),
        "facts": m,
        "facts_lines": fact_lines(m),
        "status_choices": STATUS_CHOICES,
    }


class ReportExportIn(BaseModel):
    message: str = ""          # 팀장에게 한마디(사람 입력)
    status_label: str = ""     # 선택적 한 줄 상태


@router.post("/projects/{pid}/report/export")
def report_export(pid: int, body: ReportExportIn):
    with connect() as c:
        p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        m = compute_metrics(c, p)
        author = _get_setting(c, "author_name", "")

    ts = now()
    # 사람이 열어도 보이는 요약 블록
    human = []
    human.append("[ 업무 진행상황 보고 ]")
    human.append(f"업무: {m['name']}  ({m['doc_type'] or '문서유형 미정'})")
    human.append(f"보고자: {author or '(이름 미설정)'}")
    human.append(f"작성시각: {ts}")
    if body.status_label:
        human.append(f"상태: {body.status_label}")
    human.append("")
    human += fact_lines(m)
    human.append("")
    human.append("[ 보고자 의견 ]")
    human.append(body.message.strip() or "(없음)")

    report = {
        "type": "workbench-progress-report",
        "version": 1,
        "author": author,
        "generated_at": ts,
        "project": m,
        "status_label": body.status_label,
        "message": body.message.strip(),
        "human_summary": "\n".join(human),
    }
    data = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")

    def safe(s):
        return "".join(ch for ch in (s or "") if ch not in '\\/:*?"<>|').strip()
    datestr = datetime.now().strftime("%Y%m%d")
    who = safe(author) or "보고자"
    what = safe(m["name"])[:24] or "업무"
    filename = f"진행보고_{who}_{what}_{datestr}.json"
    quoted = urllib.parse.quote(filename)
    return Response(
        content=data,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
