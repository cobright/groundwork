# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect, now
from ..agents.fact_check import review_facts
from ..agents.technical import review_technical
from ..agents.structure import review_structure
from ..agents.critique import review_critique, PERSPECTIVES
from ..agents.common import assemble_document

router = APIRouter(prefix="/api/projects", tags=["review"])

KINDS = ("사실확인", "기술검토", "구조검토", "비평")


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _linked_evidence(c, pid, uid):
    rows = c.execute("SELECT * FROM evidence WHERE project_id=? AND node_uid=? ORDER BY id", (pid, uid)).fetchall()
    out = []
    for e in rows:
        d = dict(e)
        if d.get("resource_id"):
            r = c.execute("SELECT name FROM resources WHERE id=?", (d["resource_id"],)).fetchone()
            a = c.execute("SELECT summary,state FROM resource_analysis WHERE resource_id=?", (d["resource_id"],)).fetchone()
            d["resource_name"] = r["name"] if r else ""
            d["resource_summary"] = a["summary"] if a else ""
            d["state"] = a["state"] if a else "분석 전"
        else:
            d["resource_name"] = ""; d["resource_summary"] = ""; d["state"] = ""
        out.append(d)
    return out


def _title_and_number(c, pid, uid):
    nodes = c.execute("SELECT uid,parent_uid,sort,title FROM outline_nodes WHERE project_id=? ORDER BY sort", (pid,)).fetchall()
    title = next((n["title"] for n in nodes if n["uid"] == uid), "")
    children = {}
    for n in nodes:
        children.setdefault(n["parent_uid"], []).append(n)
    for a in children.values():
        a.sort(key=lambda x: x["sort"])
    number = {}
    def walk(parent, prefix):
        for i, n in enumerate(children.get(parent, [])):
            num = f"{prefix}{i+1}"; number[n["uid"]] = num; walk(n["uid"], num + ".")
    walk(None, "")
    return title, number.get(uid, "")


def _all_sections(c, pid):
    """문서 전체 검토용: 목차 순서대로 {uid,number,title,body} 목록."""
    nodes = c.execute("SELECT uid,parent_uid,sort,title FROM outline_nodes WHERE project_id=? ORDER BY sort", (pid,)).fetchall()
    children = {}
    for n in nodes:
        children.setdefault(n["parent_uid"], []).append(n)
    for a in children.values():
        a.sort(key=lambda x: x["sort"])
    number = {}
    order = []
    def walk(parent, prefix):
        for i, n in enumerate(children.get(parent, [])):
            num = f"{prefix}{i+1}"; number[n["uid"]] = num; order.append(n); walk(n["uid"], num + ".")
    walk(None, "")
    out = []
    for n in order:
        d = c.execute("SELECT body FROM drafts WHERE project_id=? AND node_uid=?", (pid, n["uid"])).fetchone()
        out.append({"uid": n["uid"], "number": number[n["uid"]], "title": n["title"], "body": d["body"] if d else ""})
    return out


def _save_opinions(pid, uid, kind, opinions):
    """재실행 시 같은 종류의 '미처리 AI 의견'만 정리하고 새로 저장(사용자 처리분 보존).
    uid=None 이면 문서 전체(node_uid IS NULL) 대상."""
    with connect() as c:
        if uid is None:
            c.execute("DELETE FROM review_opinions WHERE project_id=? AND node_uid IS NULL AND kind=? AND source='AI' AND status='미처리'", (pid, kind))
        else:
            c.execute("DELETE FROM review_opinions WHERE project_id=? AND node_uid=? AND kind=? AND source='AI' AND status='미처리'", (pid, uid, kind))
        n = 0
        for o in opinions:
            c.execute(
                """INSERT INTO review_opinions(project_id,node_uid,kind,severity,target_text,problem,suggestion,basis,needs,status,source,model,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, uid, o["kind"], o["severity"], o["target_text"], o["problem"], o["suggestion"],
                 o["basis"], o["needs"], "미처리", o["source"], o["model"], now()),
            )
            n += 1
    return n


def _run_kind(kind, scope_label, content, evidences, title, number, perspective, provider):
    if kind == "사실확인":
        return review_facts(title, number, content, evidences, provider)
    if kind == "기술검토":
        return review_technical(scope_label, content, provider)
    if kind == "구조검토":
        return review_structure(scope_label, content, provider)
    if kind == "비평":
        return review_critique(scope_label, content, perspective, provider)
    raise HTTPException(400, "알 수 없는 검토 종류입니다.")


class ReviewRunIn(BaseModel):
    kind: str = "사실확인"          # 사실확인/기술검토/구조검토/비평
    provider: str | None = None
    perspective: str = "군수"       # 비평에서 사용할 관점


# ── 목차별 검토 ──
@router.post("/{pid}/nodes/{uid}/review/run")
def run_review_node(pid: int, uid: str, body: ReviewRunIn):
    if body.kind not in KINDS:
        raise HTTPException(400, "알 수 없는 검토 종류입니다.")
    with connect() as c:
        _require(c, pid)
        if not c.execute("SELECT 1 FROM outline_nodes WHERE project_id=? AND uid=?", (pid, uid)).fetchone():
            raise HTTPException(404, "목차 항목을 찾을 수 없습니다.")
        d = c.execute("SELECT body FROM drafts WHERE project_id=? AND node_uid=?", (pid, uid)).fetchone()
        draft_body = d["body"] if d else ""
        ev = _linked_evidence(c, pid, uid)
        title, number = _title_and_number(c, pid, uid)
    if not draft_body.strip():
        raise HTTPException(400, "이 목차에는 아직 확정된 본문이 없습니다. 먼저 초고를 작성하세요.")
    scope_label = f"목차 {number} {title}"
    try:
        opinions = _run_kind(body.kind, scope_label, draft_body, ev, title, number, body.perspective, body.provider)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"검토 실행 실패: {e}")
    created = _save_opinions(pid, uid, body.kind, opinions)
    return {"created": created, "kind": body.kind, "scope": "목차"}


# ── 문서 전체 검토 ──
@router.post("/{pid}/review/run")
def run_review_whole(pid: int, body: ReviewRunIn):
    if body.kind not in KINDS:
        raise HTTPException(400, "알 수 없는 검토 종류입니다.")
    if body.kind == "사실확인":
        raise HTTPException(400, "사실확인은 목차별로 실행하세요(문장↔근거 대조는 목차 단위가 정확합니다).")
    with connect() as c:
        _require(c, pid)
        sections = _all_sections(c, pid)
    filled = [s for s in sections if (s.get("body") or "").strip()]
    if not filled:
        raise HTTPException(400, "확정된 본문이 있는 목차가 없습니다. 먼저 초고를 작성하세요.")
    content = assemble_document(sections)
    try:
        opinions = _run_kind(body.kind, "문서 전체", content, [], "", "", body.perspective, body.provider)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"검토 실행 실패: {e}")
    created = _save_opinions(pid, None, body.kind, opinions)
    return {"created": created, "kind": body.kind, "scope": "전체"}


@router.get("/{pid}/review/perspectives")
def critique_perspectives(pid: int):
    return {"perspectives": list(PERSPECTIVES.keys())}


# ────────────── 검토의견 조회·처리 ──────────────
@router.get("/{pid}/review")
def list_review(pid: int):
    with connect() as c:
        _require(c, pid)
        rows = c.execute("SELECT * FROM review_opinions WHERE project_id=? ORDER BY id DESC", (pid,)).fetchall()
    return [dict(r) for r in rows]


class OpinionPatch(BaseModel):
    status: str | None = None
    user_note: str | None = None


@router.put("/{pid}/review/{oid}")
def patch_opinion(pid: int, oid: int, patch: OpinionPatch):
    with connect() as c:
        _require(c, pid)
        row = c.execute("SELECT * FROM review_opinions WHERE id=? AND project_id=?", (oid, pid)).fetchone()
        if not row:
            raise HTTPException(404, "검토의견을 찾을 수 없습니다.")
        status = patch.status if patch.status is not None else row["status"]
        note = patch.user_note if patch.user_note is not None else row["user_note"]
        c.execute("UPDATE review_opinions SET status=?, user_note=? WHERE id=?", (status, note, oid))
        row = c.execute("SELECT * FROM review_opinions WHERE id=?", (oid,)).fetchone()
    return dict(row)


@router.delete("/{pid}/review/{oid}")
def delete_opinion(pid: int, oid: int):
    with connect() as c:
        _require(c, pid)
        c.execute("DELETE FROM review_opinions WHERE id=? AND project_id=?", (oid, pid))
    return {"deleted": oid}
