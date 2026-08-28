# -*- coding: utf-8 -*-
import io
import json
import urllib.parse
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from ..db import connect, now
from .dashboard import compute_metrics

router = APIRouter(prefix="/api", tags=["report"])

STATUS_CHOICES = ["정상 추진", "지연 우려", "협의·대기", "보류"]


# ────────────── 설정: 내 이름(작성자) ──────────────
def _get_setting(c, key, default=""):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


class SettingsIn(BaseModel):
    author_name: str | None = None


@router.get("/settings")
def get_settings():
    with connect() as c:
        return {"author_name": _get_setting(c, "author_name", "")}


@router.put("/settings")
def put_settings(s: SettingsIn):
    with connect() as c:
        if s.author_name is not None:
            c.execute(
                "INSERT INTO settings(key,value) VALUES('author_name',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (s.author_name.strip(),))
        return {"author_name": _get_setting(c, "author_name", "")}


# ────────────── 진행상황 보고 ──────────────
def _facts_lines(m):
    """사람이 읽는 요약 줄들(파일을 직접 열어도 보이도록)."""
    due = m["due_date"] or "미정"
    dday = "" if m["d_day"] is None else (f"(마감 {abs(m['d_day'])}일 지남)" if m["d_day"] < 0 else f"(D-{m['d_day']})")
    lines = [
        f"단계: {m['stage_label']}  ·  진행률: 본문 {m['bodies_filled']}/{m['outline_total']}",
        f"마감: {due} {dday}".rstrip(),
    ]
    issues = []
    if m["severe"]:
        issues.append(f"중대·중요 미해결 검토의견 {m['severe']}건")
    if m["unresolved"] - m["severe"] > 0:
        issues.append(f"기타 미해결 의견 {m['unresolved'] - m['severe']}건")
    if m["need_flags"]:
        issues.append(f"확인 필요 표시 {m['need_flags']}건")
    if m["ev_unconfirmed"]:
        issues.append(f"미확정 근거 {m['ev_unconfirmed']}건")
    if m["ev_changed"]:
        issues.append(f"변경된 근거 {m['ev_changed']}건")
    if m["req_open"]:
        issues.append(f"자료 회신 대기 {m['req_open']}건")
    if m["req_overdue"]:
        issues.append(f"요청 마감 초과 {m['req_overdue']}건")
    lines.append("미해결: " + (", ".join(issues) if issues else "없음"))
    return lines


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
        "facts_lines": _facts_lines(m),
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
    human += _facts_lines(m)
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
