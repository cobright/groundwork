# -*- coding: utf-8 -*-
import re
from datetime import date
from fastapi import APIRouter
from ..db import connect

router = APIRouter(prefix="/api", tags=["dashboard"])

_NEED_RE = re.compile(r"\[확인\s*필요(?::[^\]]*)?\]|\[추정[^\]]*\]")


def _today():
    return date.today().isoformat()


def _d_day(due: str):
    if not due:
        return None
    try:
        return (date.fromisoformat(due) - date.today()).days
    except Exception:
        return None


def _stage(outline_total, bodies_filled, unresolved, has_final_blockers):
    if outline_total == 0:
        return "목차 준비", 0
    if bodies_filled == 0:
        return "초고 작성 전", 10
    if bodies_filled < outline_total:
        return "초고 작성", 20 + int(50 * bodies_filled / outline_total)
    if unresolved > 0:
        return "검토 중", 75
    if has_final_blockers:
        return "정리 중", 90
    return "마무리 단계", 100


@router.get("/dashboard")
def dashboard():
    today = _today()
    out = []
    with connect() as c:
        projects = c.execute("SELECT * FROM projects ORDER BY updated_at DESC, id DESC").fetchall()
        for p in projects:
            out.append(compute_metrics(c, p))
    # 정렬: 마감 초과 → 마감 임박(가까운 순) → 미해결 많은 순
    def key(x):
        dd = x["d_day"]
        overdue_rank = 0 if x["overdue"] else 1
        due_rank = dd if dd is not None else 9999
        return (overdue_rank, due_rank, -x["blockers"], -x["unresolved"])
    out.sort(key=key)
    return {"today": today, "projects": out}


def compute_metrics(c, p):
    """한 업무의 진행 지표를 계산해 dict 로 반환(대시보드·진행보고 공용)."""
    pid = p["id"]
    outline_total = c.execute("SELECT COUNT(*) n FROM outline_nodes WHERE project_id=?", (pid,)).fetchone()["n"]
    bodies = c.execute("SELECT node_uid, body FROM drafts WHERE project_id=?", (pid,)).fetchall()
    bodies_filled = sum(1 for b in bodies if (b["body"] or "").strip())
    need_flags = sum(len(_NEED_RE.findall(b["body"] or "")) for b in bodies)

    unresolved = c.execute(
        "SELECT COUNT(*) n FROM review_opinions WHERE project_id=? AND status IN ('미처리','확인중')", (pid,)).fetchone()["n"]
    severe = c.execute(
        "SELECT COUNT(*) n FROM review_opinions WHERE project_id=? AND status IN ('미처리','확인중') AND severity IN ('중대','중요')", (pid,)).fetchone()["n"]

    ev_unconfirmed = c.execute(
        "SELECT COUNT(*) n FROM evidence e WHERE e.project_id=? AND ("
        "  e.resource_id IS NULL OR NOT EXISTS("
        "     SELECT 1 FROM resource_analysis a WHERE a.resource_id=e.resource_id AND a.state='사용자 확정'))",
        (pid,)).fetchone()["n"]
    ev_changed = c.execute(
        "SELECT COUNT(*) n FROM evidence WHERE project_id=? AND source_changed=1", (pid,)).fetchone()["n"]

    req_open = c.execute(
        "SELECT COUNT(*) n FROM data_requests WHERE project_id=? AND status IN ('필요','요청함')", (pid,)).fetchone()["n"]
    req_overdue = c.execute(
        "SELECT COUNT(*) n FROM data_requests WHERE project_id=? AND status IN ('필요','요청함') AND due_date<>'' AND due_date<?",
        (pid, _today())).fetchone()["n"]

    has_final_blockers = bool(need_flags or severe or ev_changed or (outline_total and bodies_filled < outline_total))
    stage_label, progress = _stage(outline_total, bodies_filled, unresolved, has_final_blockers)
    stage_index = {"목차 준비": 0, "초고 작성 전": 1, "초고 작성": 1, "검토 중": 2, "정리 중": 3, "마무리 단계": 4}.get(stage_label, 0)
    dd = _d_day(p["due_date"])

    return {
        "id": pid, "name": p["name"], "doc_type": p["doc_type"], "due_date": p["due_date"],
        "d_day": dd, "overdue": (dd is not None and dd < 0),
        "stage_label": stage_label, "progress": progress, "stage_index": stage_index,
        "outline_total": outline_total, "bodies_filled": bodies_filled,
        "need_flags": need_flags, "unresolved": unresolved, "severe": severe,
        "ev_unconfirmed": ev_unconfirmed, "ev_changed": ev_changed,
        "req_open": req_open, "req_overdue": req_overdue,
        "blockers": severe + ev_changed + req_overdue,
    }
