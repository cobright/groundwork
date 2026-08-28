# -*- coding: utf-8 -*-
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect, now
from ..skills.resource_analysis import analyze_resource

router = APIRouter(prefix="/api/projects", tags=["resources"])


# ────────────── 자료실 ──────────────
class ResourceIn(BaseModel):
    name: str = ""
    kind: str = "내부자료"
    source_org: str = ""
    base_date: str = ""
    trust: str = "보통"
    text: str = ""


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _analysis_dict(row):
    if not row:
        return {"state": "분석 전"}
    d = dict(row)
    for k in ("key_points", "usable_for", "cautions"):
        try:
            d[k] = json.loads(d[k])
        except Exception:
            d[k] = []
    return d


@router.get("/{pid}/resources")
def list_resources(pid: int):
    with connect() as c:
        _require(c, pid)
        own = c.execute("SELECT * FROM resources WHERE project_id=? ORDER BY id DESC", (pid,)).fetchall()
        refs = c.execute(
            "SELECT r.* FROM resources r JOIN resource_refs rf ON r.id=rf.resource_id "
            "WHERE rf.project_id=? ORDER BY r.id DESC", (pid,)
        ).fetchall()
        out = []
        for r in own:
            a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (r["id"],)).fetchone()
            item = dict(r); item["analysis"] = _analysis_dict(a); item["source"] = "own"
            out.append(item)
        for r in refs:
            a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (r["id"],)).fetchone()
            item = dict(r); item["analysis"] = _analysis_dict(a); item["source"] = "library"
            dep = c.execute("SELECT name FROM departments WHERE id=?", (r["dept_id"],)).fetchone()
            item["dept_name"] = dep["name"] if dep else ""
            out.append(item)
    return out


@router.post("/{pid}/resources", status_code=201)
def add_resource(pid: int, r: ResourceIn):
    with connect() as c:
        _require(c, pid)
        cur = c.execute(
            "INSERT INTO resources(project_id,name,kind,source_org,base_date,trust,text,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (pid, r.name.strip() or "제목 없는 자료", r.kind, r.source_org.strip(), r.base_date.strip(), r.trust, r.text, now()),
        )
        row = c.execute("SELECT * FROM resources WHERE id=?", (cur.lastrowid,)).fetchone()
    item = dict(row); item["analysis"] = {"state": "분석 전"}; item["source"] = "own"
    return item


@router.put("/{pid}/resources/{rid}")
def update_resource(pid: int, rid: int, r: ResourceIn):
    """자료 수정. 내용이 바뀌면 확정을 자동 해제하고(재분석 필요), 분석 내용 자체는 남긴다.
    이 자료를 근거로 쓰는 근거표 항목에는 '근거 자료 변경됨' 신호를 켠다."""
    with connect() as c:
        _require(c, pid)
        cur = c.execute("SELECT * FROM resources WHERE id=? AND project_id=?", (rid, pid)).fetchone()
        if not cur:
            raise HTTPException(404, "자료를 찾을 수 없습니다.")
        # 실질적 변경 여부(제목·기준일·본문·기관·유형 중 하나라도 바뀌었는지)
        changed = (
            cur["name"] != (r.name.strip() or "제목 없는 자료") or cur["kind"] != r.kind or
            cur["source_org"] != r.source_org.strip() or cur["base_date"] != r.base_date.strip() or
            cur["trust"] != r.trust or cur["text"] != r.text
        )
        c.execute(
            "UPDATE resources SET name=?, kind=?, source_org=?, base_date=?, trust=?, text=? WHERE id=?",
            (r.name.strip() or "제목 없는 자료", r.kind, r.source_org.strip(), r.base_date.strip(), r.trust, r.text, rid),
        )
        if changed:
            a = c.execute("SELECT state FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
            # 분석이 있었다면 확정을 풀고 '재분석 필요'로. 요약 등 내용은 그대로 둔다.
            if a and a["state"] in ("분석 완료", "사용자 확정"):
                c.execute("UPDATE resource_analysis SET state='재분석 필요' WHERE resource_id=?", (rid,))
            # 이 자료를 근거로 쓰는 근거표 항목에 변경 신호(참조 업무 포함)
            c.execute("UPDATE evidence SET source_changed=1 WHERE resource_id=?", (rid,))
        row = c.execute("SELECT * FROM resources WHERE id=?", (rid,)).fetchone()
        a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
    item = dict(row); item["analysis"] = _analysis_dict(a)
    return item


@router.delete("/{pid}/resources/{rid}")
def delete_resource(pid: int, rid: int):
    with connect() as c:
        _require(c, pid)
        c.execute("DELETE FROM resources WHERE id=? AND project_id=?", (rid, pid))
    return {"deleted": rid}


# ────────────── 공통자료 참조(빌려쓰기) ──────────────
class RefIn(BaseModel):
    resource_id: int


class PromoteIn(BaseModel):
    dept_id: int


@router.post("/{pid}/resources/{rid}/promote")
def promote_resource(pid: int, rid: int, body: PromoteIn):
    """업무 고유 자료를 부서 폴더(공통자료실)로 승격.
    자료의 집을 업무→공통자료실로 옮기고(원본 이동), 원래 업무는 참조로 바뀐다.
    자료 id가 그대로이므로 분석·확정·근거 연결이 자연히 보존된다."""
    with connect() as c:
        _require(c, pid)
        r = c.execute("SELECT * FROM resources WHERE id=? AND project_id=?", (rid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "이 업무의 자료가 아닙니다(공통자료는 승격할 수 없습니다).")
        if r["dept_id"] is not None:
            raise HTTPException(400, "이미 공통자료실의 자료입니다.")
        if not c.execute("SELECT id FROM departments WHERE id=?", (body.dept_id,)).fetchone():
            raise HTTPException(400, "부서 폴더를 찾을 수 없습니다.")
        # 집을 옮긴다: project_id 해제, dept_id 설정
        c.execute("UPDATE resources SET project_id=NULL, dept_id=? WHERE id=?", (body.dept_id, rid))
        # 원래 업무는 참조로 유지
        c.execute("INSERT OR IGNORE INTO resource_refs(project_id,resource_id,created_at) VALUES(?,?,?)",
                  (pid, rid, now()))
        dep = c.execute("SELECT name FROM departments WHERE id=?", (body.dept_id,)).fetchone()
    return {"promoted": rid, "dept_id": body.dept_id, "dept_name": dep["name"] if dep else ""}


@router.post("/{pid}/resource-refs", status_code=201)
def add_reference(pid: int, body: RefIn):
    """공통자료실의 자료를 이 업무에서 참조(복사 아님)."""
    with connect() as c:
        _require(c, pid)
        r = c.execute("SELECT id FROM resources WHERE id=? AND dept_id IS NOT NULL", (body.resource_id,)).fetchone()
        if not r:
            raise HTTPException(400, "공통자료실의 자료가 아닙니다.")
        c.execute("INSERT OR IGNORE INTO resource_refs(project_id,resource_id,created_at) VALUES(?,?,?)",
                  (pid, body.resource_id, now()))
    return {"linked": body.resource_id}


@router.delete("/{pid}/resource-refs/{rid}")
def remove_reference(pid: int, rid: int):
    """참조 해제(원본은 공통자료실에 남는다). 근거표에서 이 자료를 쓰던 연결은 사용자가 정리."""
    with connect() as c:
        _require(c, pid)
        c.execute("DELETE FROM resource_refs WHERE project_id=? AND resource_id=?", (pid, rid))
    return {"unlinked": rid}


# ────────────── AI 자료분석 (확정 전엔 근거 아님) ──────────────
class AnalyzeIn(BaseModel):
    provider: str | None = None   # openai/claude/gemini, 없으면 .env 기본값


@router.post("/{pid}/resources/{rid}/analyze")
def analyze(pid: int, rid: int, body: AnalyzeIn):
    with connect() as c:
        _require(c, pid)
        r = c.execute("SELECT * FROM resources WHERE id=? AND project_id=?", (rid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "자료를 찾을 수 없습니다.")
    try:
        result = analyze_resource(r["name"], r["kind"], r["source_org"], r["base_date"], r["text"], body.provider)
    except Exception as e:
        # 키 미설정·네트워크 등: 사용자에게 그대로 알린다(하네스가 삼키지 않음)
        raise HTTPException(502, f"AI 분석 실패: {e}")
    with connect() as c:
        c.execute(
            """INSERT INTO resource_analysis(resource_id,summary,key_points,usable_for,cautions,state,model,analyzed_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(resource_id) DO UPDATE SET
                 summary=excluded.summary, key_points=excluded.key_points, usable_for=excluded.usable_for,
                 cautions=excluded.cautions, state=excluded.state, model=excluded.model, analyzed_at=excluded.analyzed_at""",
            (rid, result["summary"], json.dumps(result["key_points"], ensure_ascii=False),
             json.dumps(result["usable_for"], ensure_ascii=False), json.dumps(result["cautions"], ensure_ascii=False),
             "분석 완료", result["model"], now()),
        )
        a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
    return _analysis_dict(a)


@router.post("/{pid}/resources/{rid}/confirm")
def confirm_analysis(pid: int, rid: int):
    """사용자 확정: 이때부터 근거표에서 이 자료를 공식 근거로 쓸 수 있다."""
    with connect() as c:
        _require(c, pid)
        a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
        if not a:
            raise HTTPException(400, "먼저 AI 분석을 실행하세요.")
        c.execute("UPDATE resource_analysis SET state='사용자 확정' WHERE resource_id=?", (rid,))
        a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
    return _analysis_dict(a)


# ────────────── 근거표 ──────────────
class EvidenceIn(BaseModel):
    claim: str = ""
    resource_id: int | None = None
    locator: str = ""
    trust: str = ""
    status: str = "확인 필요"
    node_uid: str | None = None


@router.get("/{pid}/evidence")
def list_evidence(pid: int):
    with connect() as c:
        _require(c, pid)
        rows = c.execute("SELECT * FROM evidence WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    return [dict(r) for r in rows]


@router.post("/{pid}/evidence", status_code=201)
def add_evidence(pid: int, e: EvidenceIn):
    with connect() as c:
        _require(c, pid)
        if e.resource_id is not None:
            ok = c.execute("SELECT 1 FROM resources WHERE id=? AND project_id=?", (e.resource_id, pid)).fetchone() or \
                 c.execute("SELECT 1 FROM resource_refs WHERE project_id=? AND resource_id=?", (pid, e.resource_id)).fetchone()
            if not ok:
                raise HTTPException(400, "연결하려는 자료가 이 업무에 없습니다(직접 등록했거나 공통자료실에서 참조한 자료여야 합니다).")
        cur = c.execute(
            "INSERT INTO evidence(project_id,claim,resource_id,locator,trust,status,node_uid,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (pid, e.claim.strip(), e.resource_id, e.locator.strip(), e.trust.strip(), e.status, e.node_uid, now()),
        )
        row = c.execute("SELECT * FROM evidence WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.put("/{pid}/evidence/{eid}")
def update_evidence(pid: int, eid: int, e: EvidenceIn):
    with connect() as c:
        _require(c, pid)
        if not c.execute("SELECT id FROM evidence WHERE id=? AND project_id=?", (eid, pid)).fetchone():
            raise HTTPException(404, "근거 항목을 찾을 수 없습니다.")
        c.execute(
            "UPDATE evidence SET claim=?, resource_id=?, locator=?, trust=?, status=?, node_uid=?, source_changed=0 WHERE id=? AND project_id=?",
            (e.claim.strip(), e.resource_id, e.locator.strip(), e.trust.strip(), e.status, e.node_uid, eid, pid),
        )
        row = c.execute("SELECT * FROM evidence WHERE id=?", (eid,)).fetchone()
    return dict(row)


@router.delete("/{pid}/evidence/{eid}")
def delete_evidence(pid: int, eid: int):
    with connect() as c:
        _require(c, pid)
        c.execute("DELETE FROM evidence WHERE id=? AND project_id=?", (eid, pid))
    return {"deleted": eid}
