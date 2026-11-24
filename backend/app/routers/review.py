# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect, now
from ..agents.fact_check import review_facts
from ..agents.technical import review_technical
from ..agents.structure import review_structure
from ..agents.critique import review_critique, PERSPECTIVES
from ..agents.common import assemble_document
from ..services.numbering import title_and_number, sections_with_body
from ..services.evidence import linked_evidence

router = APIRouter(prefix="/api/projects", tags=["review"])

KINDS = ("사실확인", "기술검토", "구조검토", "비평")


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


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
    perspective: str = "기관장"       # 비평에서 사용할 관점


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
        ev = linked_evidence(c, pid, uid)
        title, number = title_and_number(c, pid, uid)
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
        sections = sections_with_body(c, pid)
    filled = [s for s in sections if (s.get("body") or "").strip()]
    if not filled:
        raise HTTPException(400, "확정된 본문이 있는 목차가 없습니다. 먼저 초고를 작성하세요.")
    content, truncated = assemble_document(sections)
    try:
        opinions = _run_kind(body.kind, "문서 전체", content, [], "", "", body.perspective, body.provider)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"검토 실행 실패: {e}")
    created = _save_opinions(pid, None, body.kind, opinions)
    return {"created": created, "kind": body.kind, "scope": "전체", "truncated": truncated}


@router.get("/{pid}/review/perspectives")
def critique_perspectives(pid: int):
    return {"perspectives": list(PERSPECTIVES.keys())}


# ────────────── 검토의견 조회·처리 ──────────────
@router.get("/{pid}/review")
def list_review(pid: int):
    with connect() as c:
        _require(c, pid)
        rows = c.execute("SELECT * FROM review_opinions WHERE project_id=? ORDER BY id DESC", (pid,)).fetchall()
        # 이 의견이 이미 자료요청으로 넘어갔는지. 같은 의견을 두 번 요청하지 않도록
        # 화면에서 바로 보여준다(중복 방지 키는 자동수집과 같은 'op:{id}' 다).
        made = {r["origin_ref"]: r for r in c.execute(
            "SELECT id,origin_ref,status,need FROM data_requests "
            "WHERE project_id=? AND origin='review' AND origin_ref<>''", (pid,)).fetchall()}
    out = []
    for r in rows:
        d = dict(r)
        q = made.get(f"op:{r['id']}")
        d["request_id"] = q["id"] if q else None
        d["request_status"] = q["status"] if q else ""
        out.append(d)
    return out


class ToRequestIn(BaseModel):
    need: str | None = None       # 비우면 의견의 '필요조치'(없으면 문제 내용)를 쓴다
    dept_id: int | None = None


@router.post("/{pid}/review/{oid}/to-request", status_code=201)
def opinion_to_request(pid: int, oid: int, body: ToRequestIn):
    """검토의견을 그 자리에서 자료요청으로 잇는다.

    지금까지는 검토에서 '자료가 필요하다'는 것을 알고도 자료요청 화면으로 건너가
    <자동 수집>을 다시 눌러야 했다. 게다가 자동 수집은 **필요조치(needs)가 적힌 의견만**
    가져오므로, 그 칸이 빈 의견은 아예 넘어오지 않았다. 이 문은 그 둘을 다 푼다.

    중복 방지 키(`origin_ref = 'op:{id}'`)를 자동 수집과 **같은 것**으로 쓴다.
    다르면 여기서 만든 요청이 자동 수집에서 한 번 더 만들어진다.
    """
    with connect() as c:
        _require(c, pid)
        o = c.execute("SELECT * FROM review_opinions WHERE id=? AND project_id=?", (oid, pid)).fetchone()
        if not o:
            raise HTTPException(404, "검토의견을 찾을 수 없습니다.")
        ref = f"op:{oid}"
        old = c.execute("SELECT id,need,status FROM data_requests WHERE project_id=? AND origin_ref=?",
                        (pid, ref)).fetchone()
        if old:
            return {"request_id": old["id"], "need": old["need"], "status": old["status"], "already": True}
        need = (body.need or "").strip() or (o["needs"] or "").strip() or (o["problem"] or "").strip()
        if not need:
            raise HTTPException(400, "요청할 내용이 비어 있습니다. 무엇이 필요한지 적어 주세요.")
        note = f"[{o['kind']}] {(o['problem'] or '')[:60]}"
        cur = c.execute(
            "INSERT INTO data_requests(project_id,node_uid,need,dept_id,status,origin,origin_ref,note,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (pid, o["node_uid"], need[:300], body.dept_id, "필요", "review", ref, note, now()))
        rid = cur.lastrowid
    return {"request_id": rid, "need": need, "status": "필요", "already": False}


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
