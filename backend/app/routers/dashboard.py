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


# 막힌 곳 한 줄의 모양: (순위, 종류, 갈 곳, 무엇을 해야 하는지)
# 세는 것은 이미 compute_metrics 가 다 한다 — 여기서는 **모으고, 할 일을 붙이기만** 한다.
# 숫자만 보여주면 "그래서 뭘 하라는 건가"가 남는다(원칙 5: 통제되고 있다는 느낌).
def _blocked_rows(m: dict) -> list[dict]:
    rows = []

    def add(rank, kind, count, what, tab):
        rows.append({"rank": rank, "project_id": m["id"], "project_name": m["name"],
                     "kind": kind, "count": count, "what": what, "tab": tab})

    if m["overdue"]:
        add(0, "마감 초과", abs(m["d_day"]),
            f"마감일이 {abs(m['d_day'])}일 지났습니다. 마감을 다시 잡거나 보관함에 넣으세요.", "final")
    elif m["d_day"] is not None and m["d_day"] <= 3:
        add(1, "마감 임박", m["d_day"],
            ("오늘이 마감입니다." if m["d_day"] == 0 else f"마감까지 {m['d_day']}일 남았습니다."), "final")
    if m["req_overdue"]:
        add(2, "회신 기한 초과", m["req_overdue"],
            "부서에 요청한 자료의 회신 기한이 지났습니다. 다시 요청하거나 기한을 조정하세요.", "requests")
    if m["ev_changed"]:
        add(3, "근거 자료 바뀜", m["ev_changed"],
            "근거로 쓴 자료가 수정됐습니다. 원문을 다시 보고 ‘확인함’을 눌러 주세요.", "resources")
    if m["severe"]:
        add(4, "중대·중요 검토의견", m["severe"],
            "처리하지 않으면 최종본 점검에서 막힙니다.", "review")
    return rows


@router.get("/dashboard")
def dashboard():
    today = _today()
    out = []
    with connect() as c:
        # 보관함(캐비넷)에 든 업무는 상황판에서 뺀다 — 지금 관리 대상이 아니다.
        projects = c.execute(
            "SELECT * FROM projects WHERE archived_at='' ORDER BY updated_at DESC, id DESC").fetchall()
        for p in projects:
            out.append(compute_metrics(c, p))
    # 정렬: 마감 초과 → 마감 임박(가까운 순) → 미해결 많은 순
    def key(x):
        dd = x["d_day"]
        overdue_rank = 0 if x["overdue"] else 1
        due_rank = dd if dd is not None else 9999
        return (overdue_rank, due_rank, -x["blockers"], -x["unresolved"])
    out.sort(key=key)
    blocked = [r for m in out for r in _blocked_rows(m)]
    blocked.sort(key=lambda r: (r["rank"], -r["count"]))
    return {"today": today, "projects": out, "blocked": blocked}


def compute_metrics(c, p):
    """한 업무의 진행 지표를 계산해 dict 로 반환(대시보드·진행보고 공용)."""
    pid = p["id"]
    outline_total = c.execute("SELECT COUNT(*) n FROM outline_nodes WHERE project_id=?", (pid,)).fetchone()["n"]
    # 목차에 남아 있는 항목의 본문만 센다(지워진 목차의 본문이 진행률을 부풀리지 않도록)
    bodies = c.execute(
        "SELECT d.node_uid, d.body FROM drafts d "
        "JOIN outline_nodes o ON o.project_id=d.project_id AND o.uid=d.node_uid "
        "WHERE d.project_id=?", (pid,)).fetchall()
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
