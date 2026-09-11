# -*- coding: utf-8 -*-
import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from ..db import connect, now
from ..services.attachments import MAX_BYTES, file_meta, read_upload, store_file
from ..services.doc_read import ReadError
from ..skills.resource_analysis import analyze_resource

router = APIRouter(prefix="/api/library", tags=["library"])


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


def _lib_item(c, r):
    a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (r["id"],)).fetchone()
    d = dict(r); d["analysis"] = _analysis_dict(a)
    d["file"] = file_meta(c, [r["id"]]).get(r["id"])
    d["ref_count"] = c.execute("SELECT COUNT(*) c FROM resource_refs WHERE resource_id=?", (r["id"],)).fetchone()["c"]
    dep = c.execute("SELECT name FROM departments WHERE id=?", (r["dept_id"],)).fetchone()
    d["dept_name"] = dep["name"] if dep else ""
    d["source"] = "library"
    return d


# ────────────── 부서 폴더 ──────────────
class DeptIn(BaseModel):
    name: str = ""


@router.get("/departments")
def list_departments():
    with connect() as c:
        rows = c.execute(
            "SELECT d.*, (SELECT COUNT(*) FROM resources r WHERE r.dept_id=d.id) AS resource_count "
            "FROM departments d ORDER BY sort, id"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/departments", status_code=201)
def create_department(d: DeptIn):
    name = d.name.strip()
    if not name:
        raise HTTPException(400, "부서명을 입력하세요.")
    with connect() as c:
        s = c.execute("SELECT COALESCE(MAX(sort),-1)+1 s FROM departments").fetchone()["s"]
        cur = c.execute("INSERT INTO departments(name,sort,created_at) VALUES(?,?,?)", (name, s, now()))
        row = c.execute("SELECT * FROM departments WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.put("/departments/{did}")
def rename_department(did: int, d: DeptIn):
    name = d.name.strip()
    if not name:
        raise HTTPException(400, "부서명을 입력하세요.")
    with connect() as c:
        if not c.execute("SELECT id FROM departments WHERE id=?", (did,)).fetchone():
            raise HTTPException(404, "부서를 찾을 수 없습니다.")
        c.execute("UPDATE departments SET name=? WHERE id=?", (name, did))
        row = c.execute("SELECT * FROM departments WHERE id=?", (did,)).fetchone()
    return dict(row)


@router.delete("/departments/{did}")
def delete_department(did: int):
    with connect() as c:
        if not c.execute("SELECT id FROM departments WHERE id=?", (did,)).fetchone():
            raise HTTPException(404, "부서를 찾을 수 없습니다.")
        n = c.execute("SELECT COUNT(*) c FROM resources WHERE dept_id=?", (did,)).fetchone()["c"]
        if n > 0:
            raise HTTPException(409, f"이 부서 폴더에 자료 {n}건이 있어 삭제할 수 없습니다. 먼저 자료를 옮기거나 삭제하세요.")
        c.execute("DELETE FROM departments WHERE id=?", (did,))
    return {"deleted": did}


# ────────────── 공통자료 ──────────────
class LibResourceIn(BaseModel):
    dept_id: int
    name: str = ""
    kind: str = "부서자료"
    source_org: str = ""
    base_date: str = ""
    trust: str = "보통"
    text: str = ""
    note: str = ""        # 담당자 메모. 자료 '내용'이 아니므로 확정을 풀지 않는다(resources.py 와 같은 규칙).


@router.get("/resources")
def list_lib_resources(dept_id: int | None = None, q: str | None = None):
    with connect() as c:
        sql = "SELECT * FROM resources WHERE dept_id IS NOT NULL"
        args = []
        if dept_id:
            sql += " AND dept_id=?"; args.append(dept_id)
        if q and q.strip():
            kw = f"%{q.strip()}%"; sql += " AND (name LIKE ? OR text LIKE ? OR source_org LIKE ?)"; args += [kw, kw, kw]
        sql += " ORDER BY id DESC"
        rows = c.execute(sql, args).fetchall()
        out = [_lib_item(c, r) for r in rows]
    return out


@router.post("/resources", status_code=201)
def add_lib_resource(r: LibResourceIn):
    with connect() as c:
        if not c.execute("SELECT id FROM departments WHERE id=?", (r.dept_id,)).fetchone():
            raise HTTPException(400, "부서를 찾을 수 없습니다.")
        cur = c.execute(
            "INSERT INTO resources(dept_id,project_id,name,kind,source_org,base_date,trust,text,note,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (r.dept_id, None, r.name.strip() or "제목 없는 자료", r.kind, r.source_org.strip(),
             r.base_date.strip(), r.trust, r.text, r.note.strip(), now()),
        )
        row = c.execute("SELECT * FROM resources WHERE id=?", (cur.lastrowid,)).fetchone()
        item = _lib_item(c, row)
    return item


@router.post("/resources/upload", status_code=201)
async def upload_lib_resource(request: Request, dept_id: int, filename: str = "", name: str = "",
                              kind: str = "부서자료", source_org: str = "", base_date: str = "",
                              trust: str = "보통"):
    """공통자료실에 파일로 등록한다(본문 = 파일 원시 바이트).

    업무 자료(routers/resources.py)와 **같은 엔진**을 쓴다 — 형식 분기를 새로 만들지 않는다.
    공통자료는 여러 업무가 함께 참조하므로, 원본이 남아 있는 것이 업무 자료보다 더 중요하다
    (한 사람이 읽어 옮긴 글자를 여럿이 근거로 쓰게 되기 때문).
    """
    data = await request.body()
    if not data:
        raise HTTPException(400, "빈 파일입니다. 내려받기가 끊겼는지 확인해 주세요.")
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "파일이 너무 큽니다(40MB 이하).")
    try:
        info = read_upload(data, filename)
    except ReadError as e:
        raise HTTPException(400, str(e))
    with connect() as c:
        if not c.execute("SELECT id FROM departments WHERE id=?", (dept_id,)).fetchone():
            raise HTTPException(400, "부서를 찾을 수 없습니다.")
        cur = c.execute(
            "INSERT INTO resources(dept_id,project_id,name,kind,source_org,base_date,trust,text,note,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (dept_id, None, (name.strip() or filename.strip() or "올린 자료")[:120], kind,
             source_org.strip(), base_date.strip(), trust, info["text"], "", now()))
        rid = cur.lastrowid
        store_file(c, rid, data, filename, info)
        row = c.execute("SELECT * FROM resources WHERE id=?", (rid,)).fetchone()
        item = _lib_item(c, row)
    return item


@router.get("/resources/{rid}/file")
def download_lib_file(rid: int):
    """공통자료의 원본 파일. 참조하는 업무 어디서든 원문으로 되돌아갈 수 있어야 한다."""
    with connect() as c:
        if not c.execute("SELECT id FROM resources WHERE id=? AND dept_id IS NOT NULL", (rid,)).fetchone():
            raise HTTPException(404, "공통자료를 찾을 수 없습니다.")
        f = c.execute("SELECT filename,data FROM resource_files WHERE resource_id=?", (rid,)).fetchone()
    if not f:
        raise HTTPException(404, "이 자료에는 올린 원본 파일이 없습니다(붙여넣어 만든 자료입니다).")
    return Response(content=f["data"], media_type="application/octet-stream",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(f["filename"] or "자료")})


class NoteIn(BaseModel):
    note: str = ""


@router.put("/resources/{rid}/note")
def set_lib_note(rid: int, body: NoteIn):
    """담당자 메모만 고친다(자료 수정은 본문까지 통째로 받으므로 따로 둔다 — resources.py 와 같은 이유)."""
    with connect() as c:
        if not c.execute("SELECT id FROM resources WHERE id=? AND dept_id IS NOT NULL", (rid,)).fetchone():
            raise HTTPException(404, "공통자료를 찾을 수 없습니다.")
        c.execute("UPDATE resources SET note=? WHERE id=?", (body.note.strip(), rid))
    return {"id": rid, "note": body.note.strip()}


@router.put("/resources/{rid}")
def update_lib_resource(rid: int, r: LibResourceIn):
    """공통자료 수정. 내용이 바뀌면 확정 해제(재분석 필요) + '이 자료를 참조하는 모든 업무'의 근거에 변경 신호."""
    with connect() as c:
        cur = c.execute("SELECT * FROM resources WHERE id=? AND dept_id IS NOT NULL", (rid,)).fetchone()
        if not cur:
            raise HTTPException(404, "공통자료를 찾을 수 없습니다.")
        changed = (
            cur["name"] != (r.name.strip() or "제목 없는 자료") or cur["kind"] != r.kind or
            cur["source_org"] != r.source_org.strip() or cur["base_date"] != r.base_date.strip() or
            cur["trust"] != r.trust or cur["text"] != r.text
        )
        c.execute(
            "UPDATE resources SET dept_id=?, name=?, kind=?, source_org=?, base_date=?, trust=?, text=?, note=? WHERE id=?",
            (r.dept_id, r.name.strip() or "제목 없는 자료", r.kind, r.source_org.strip(),
             r.base_date.strip(), r.trust, r.text, r.note.strip(), rid),
        )
        if changed:
            a = c.execute("SELECT state FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
            if a and a["state"] in ("분석 완료", "사용자 확정"):
                c.execute("UPDATE resource_analysis SET state='재분석 필요' WHERE resource_id=?", (rid,))
            c.execute("UPDATE evidence SET source_changed=1 WHERE resource_id=?", (rid,))  # 참조 업무 전체
        row = c.execute("SELECT * FROM resources WHERE id=?", (rid,)).fetchone()
        item = _lib_item(c, row)
    return item


@router.delete("/resources/{rid}")
def delete_lib_resource(rid: int, force: bool = False):
    with connect() as c:
        if not c.execute("SELECT id FROM resources WHERE id=? AND dept_id IS NOT NULL", (rid,)).fetchone():
            raise HTTPException(404, "공통자료를 찾을 수 없습니다.")
        refs = c.execute("SELECT COUNT(*) c FROM resource_refs WHERE resource_id=?", (rid,)).fetchone()["c"]
        if refs > 0 and not force:
            raise HTTPException(409, f"이 자료를 참조하는 업무가 {refs}건 있습니다. 삭제하면 해당 업무 근거에 '원본 삭제됨' 신호가 표시됩니다. 계속하려면 확인을 눌러 주세요.")
        if refs > 0:
            c.execute("UPDATE evidence SET source_changed=1 WHERE resource_id=?", (rid,))
        c.execute("DELETE FROM resources WHERE id=?", (rid,))  # refs·analysis CASCADE, evidence.resource_id SET NULL
    return {"deleted": rid, "was_referenced": refs}


# ── 공통자료 AI 분석/확정 (한 번만 하면 참조 업무 전체가 공유) ──
class AnalyzeIn(BaseModel):
    provider: str | None = None


@router.post("/resources/{rid}/analyze")
def analyze_lib(rid: int, body: AnalyzeIn):
    with connect() as c:
        r = c.execute("SELECT * FROM resources WHERE id=? AND dept_id IS NOT NULL", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "공통자료를 찾을 수 없습니다.")
    try:
        result = analyze_resource(r["name"], r["kind"], r["source_org"], r["base_date"], r["text"], body.provider)
    except Exception as e:
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


@router.post("/resources/{rid}/confirm")
def confirm_lib(rid: int):
    with connect() as c:
        r = c.execute("SELECT id FROM resources WHERE id=? AND dept_id IS NOT NULL", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "공통자료를 찾을 수 없습니다.")
        a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
        if not a:
            raise HTTPException(400, "먼저 AI 분석을 실행하세요.")
        c.execute("UPDATE resource_analysis SET state='사용자 확정' WHERE resource_id=?", (rid,))
        a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
    return _analysis_dict(a)
