# -*- coding: utf-8 -*-
import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from ..db import connect, now
from ..skills.resource_analysis import analyze_resource, asked_missing
from ..services.attachments import MAX_BYTES, file_meta, read_upload, store_file
from ..services.doc_read import ReadError
from ..services.numbering import attach_evidence_no

router = APIRouter(prefix="/api/projects", tags=["resources"])


# ────────────── 자료실 ──────────────
class ResourceIn(BaseModel):
    name: str = ""
    kind: str = "내부자료"
    source_org: str = ""
    base_date: str = ""
    trust: str = "보통"
    text: str = ""
    note: str = ""        # 담당자 메모. 자료 '내용'이 아니라 그 자료에 대한 사람의 말이다.


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _analysis_dict(row):
    if not row:
        return {"state": "분석 전", "asked_missing": []}
    d = dict(row)
    for k in ("key_points", "usable_for", "cautions"):
        try:
            d[k] = json.loads(d[k])
        except Exception:
            d[k] = []
    d["asked_missing"] = asked_missing(d["cautions"])     # 요청했는데 회신에 없는 것
    return d


def _reply_of(c, rid: int):
    """이 자료가 어떤 자료요청의 회신인지(있으면). 화면이 '재요청으로 되돌리기'를 보일지 정한다."""
    r = c.execute("SELECT id, need, status FROM data_requests WHERE received_resource_id=?", (rid,)).fetchone()
    return dict(r) if r else None


@router.get("/{pid}/resources")
def list_resources(pid: int):
    with connect() as c:
        _require(c, pid)
        own = c.execute("SELECT * FROM resources WHERE project_id=? ORDER BY id DESC", (pid,)).fetchall()
        refs = c.execute(
            "SELECT r.* FROM resources r JOIN resource_refs rf ON r.id=rf.resource_id "
            "WHERE rf.project_id=? ORDER BY r.id DESC", (pid,)
        ).fetchall()
        files = file_meta(c, [r["id"] for r in own] + [r["id"] for r in refs])
        out = []
        for r in own:
            a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (r["id"],)).fetchone()
            item = dict(r); item["analysis"] = _analysis_dict(a); item["source"] = "own"
            item["file"] = files.get(r["id"]); item["reply_of"] = _reply_of(c, r["id"])
            out.append(item)
        for r in refs:
            a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (r["id"],)).fetchone()
            item = dict(r); item["analysis"] = _analysis_dict(a); item["file"] = files.get(r["id"])
            if r["dept_id"] is not None:
                item["source"] = "library"
                dep = c.execute("SELECT name FROM departments WHERE id=?", (r["dept_id"],)).fetchone()
                item["dept_name"] = dep["name"] if dep else ""
            else:
                # 다른 업무의 자료를 빌려 온 경우(보고전 뽑기). 공통자료실 자료가 아니다.
                item["source"] = "project"
                own = c.execute("SELECT name FROM projects WHERE id=?", (r["project_id"],)).fetchone()
                item["dept_name"] = ""
                item["owner_name"] = own["name"] if own else ""
            out.append(item)
    return out


@router.post("/{pid}/resources", status_code=201)
def add_resource(pid: int, r: ResourceIn):
    with connect() as c:
        _require(c, pid)
        cur = c.execute(
            "INSERT INTO resources(project_id,name,kind,source_org,base_date,trust,text,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (pid, r.name.strip() or "제목 없는 자료", r.kind, r.source_org.strip(), r.base_date.strip(),
             r.trust, r.text, r.note.strip(), now()),
        )
        row = c.execute("SELECT * FROM resources WHERE id=?", (cur.lastrowid,)).fetchone()
    item = dict(row); item["analysis"] = {"state": "분석 전"}; item["source"] = "own"; item["file"] = None
    return item


@router.post("/{pid}/resources/upload", status_code=201)
async def upload_resource(pid: int, request: Request, filename: str = "", name: str = "",
                          kind: str = "부서자료", source_org: str = "", base_date: str = "",
                          trust: str = "보통"):
    """파일을 올려 자료로 등록한다(본문 = 파일 원시 바이트).

    multipart 를 쓰지 않는 이유는 guidelines.py 와 같다 — python-multipart 의존성이 늘면
    담당자가 1_SETUP 을 다시 돌려야 한다.
    여기서 분석까지 하지 않는다. 읽어서 본문에 넣을 뿐이고, 분석·확정은 사람이 누른다(원칙 1).
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
        _require(c, pid)
        cur = c.execute(
            "INSERT INTO resources(project_id,name,kind,source_org,base_date,trust,text,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (pid, (name.strip() or filename.strip() or "올린 자료")[:120], kind, source_org.strip(),
             base_date.strip(), trust, info["text"], "", now()),
        )
        rid = cur.lastrowid
        store_file(c, rid, data, filename, info)
        row = c.execute("SELECT * FROM resources WHERE id=?", (rid,)).fetchone()
        files = file_meta(c, [rid])
    item = dict(row); item["analysis"] = {"state": "분석 전"}; item["source"] = "own"
    item["file"] = files.get(rid)
    return item


class NoteIn(BaseModel):
    note: str = ""


@router.put("/{pid}/resources/{rid}/note")
def set_resource_note(pid: int, rid: int, body: NoteIn):
    """담당자 메모만 고친다.

    자료 수정(PUT /resources/{rid})은 본문·기준일까지 통째로 받으므로 메모 한 줄을
    고치려고 부르면 나머지가 빈 값으로 덮인다. 자료요청 화면에서도 같은 메모를
    적을 수 있어야 하는데(회신에 대해 남길 말), 칸을 새로 만들면 같은 뜻의 자리가
    둘이 되므로 **같은 칸을 다른 문으로 여는** 쪽을 택했다.
    """
    with connect() as c:
        _require(c, pid)
        if not c.execute("SELECT id FROM resources WHERE id=? AND project_id=?", (rid, pid)).fetchone():
            raise HTTPException(404, "이 업무의 자료가 아닙니다(빌려온 자료의 메모는 그쪽에서 고칩니다).")
        c.execute("UPDATE resources SET note=? WHERE id=?", (body.note.strip(), rid))
    return {"id": rid, "note": body.note.strip()}


@router.get("/{pid}/resources/{rid}/file")
def download_resource_file(pid: int, rid: int):
    """올린 원본을 그대로 내려준다. 근거는 언제든 원문으로 되돌아갈 수 있어야 한다(원칙 2)."""
    with connect() as c:
        _require(c, pid)
        ok = c.execute("SELECT 1 FROM resources WHERE id=? AND project_id=?", (rid, pid)).fetchone() or \
             c.execute("SELECT 1 FROM resource_refs WHERE project_id=? AND resource_id=?", (pid, rid)).fetchone()
        if not ok:
            raise HTTPException(404, "이 업무의 자료가 아닙니다.")
        f = c.execute("SELECT filename,data FROM resource_files WHERE resource_id=?", (rid,)).fetchone()
    if not f:
        raise HTTPException(404, "이 자료에는 올린 원본 파일이 없습니다(붙여넣어 만든 자료입니다).")
    name = f["filename"] or "자료"
    return Response(content=f["data"], media_type="application/octet-stream",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)})


@router.put("/{pid}/resources/{rid}")
def update_resource(pid: int, rid: int, r: ResourceIn):
    """자료 수정. 내용이 바뀌면 확정을 자동 해제하고(재분석 필요), 분석 내용 자체는 남긴다.
    이 자료를 근거로 쓰는 근거표 항목에는 '근거 자료 변경됨' 신호를 켠다."""
    with connect() as c:
        _require(c, pid)
        cur = c.execute("SELECT * FROM resources WHERE id=? AND project_id=?", (rid, pid)).fetchone()
        if not cur:
            raise HTTPException(404, "자료를 찾을 수 없습니다.")
        # 실질적 변경 여부(제목·기준일·본문·기관·유형 중 하나라도 바뀌었는지).
        # 담당자 메모(note)는 자료의 내용이 아니라 그 자료를 어떻게 볼지에 대한 사람의 말이므로
        # 여기서 세지 않는다 — 메모 한 줄에 확정이 풀리고 근거마다 변경신호가 뜨면 아무도 안 쓴다.
        changed = (
            cur["name"] != (r.name.strip() or "제목 없는 자료") or cur["kind"] != r.kind or
            cur["source_org"] != r.source_org.strip() or cur["base_date"] != r.base_date.strip() or
            cur["trust"] != r.trust or cur["text"] != r.text
        )
        c.execute(
            "UPDATE resources SET name=?, kind=?, source_org=?, base_date=?, trust=?, text=?, note=? WHERE id=?",
            (r.name.strip() or "제목 없는 자료", r.kind, r.source_org.strip(), r.base_date.strip(),
             r.trust, r.text, r.note.strip(), rid),
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
        files = file_meta(c, [rid])
    item = dict(row); item["analysis"] = _analysis_dict(a); item["file"] = files.get(rid)
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
        # 부서 회신으로 들어온 자료면 '무엇을 요청했는지'를 함께 넘긴다.
        # 담당자가 대신 못 하는 일은 요약이 아니라 **요청한 것 중 빠진 것 찾기**다.
        ask = c.execute("SELECT need FROM data_requests WHERE project_id=? AND received_resource_id=?",
                        (pid, rid)).fetchone()
        asked = ask["need"] if ask else ""
    try:
        result = analyze_resource(r["name"], r["kind"], r["source_org"], r["base_date"], r["text"],
                                  body.provider, asked=asked)
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


class ConfirmIn(BaseModel):
    force: bool = False      # '요청한 것이 이 자료에 없다'는 경고를 보고도 확정한다


@router.post("/{pid}/resources/{rid}/confirm")
def confirm_analysis(pid: int, rid: int, body: ConfirmIn | None = None):
    """사용자 확정: 이때부터 근거표에서 이 자료를 공식 근거로 쓸 수 있다.

    회신 자료가 요청과 다르면(분석이 '요청한 ○○은 이 자료에 없습니다'라고 했으면) 한 번 묻는다 —
    막지는 않는다(요청과 달라도 쓸모 있는 자료일 수 있다). 판단은 사람이 한다(원칙 1)."""
    with connect() as c:
        _require(c, pid)
        a = c.execute("SELECT * FROM resource_analysis WHERE resource_id=?", (rid,)).fetchone()
        if not a:
            raise HTTPException(400, "먼저 AI 분석을 실행하세요.")
        missing = _analysis_dict(a)["asked_missing"]
        if missing and not (body and body.force):
            raise HTTPException(409, f"요청한 것 {len(missing)}가지가 이 회신 자료에 없습니다 — "
                                     + " / ".join(missing[:3])
                                     + ". 그래도 확정하시겠습니까? 다른 파일이 왔다면 ‘재요청으로 되돌리기’를 쓰세요.")
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
        out = attach_evidence_no(c, pid, [dict(r) for r in rows])
    return out


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
        item = attach_evidence_no(c, pid, [dict(row)])[0]
    return item


@router.put("/{pid}/evidence/{eid}")
def update_evidence(pid: int, eid: int, e: EvidenceIn):
    with connect() as c:
        _require(c, pid)
        if not c.execute("SELECT id FROM evidence WHERE id=? AND project_id=?", (eid, pid)).fetchone():
            raise HTTPException(404, "근거 항목을 찾을 수 없습니다.")
        # ★ source_changed 는 여기서 건드리지 않는다.
        # '근거 자료가 바뀌었다'는 신호는 사람이 원문을 확인했을 때만 꺼진다(아래 acknowledge).
        c.execute(
            "UPDATE evidence SET claim=?, resource_id=?, locator=?, trust=?, status=?, node_uid=? WHERE id=? AND project_id=?",
            (e.claim.strip(), e.resource_id, e.locator.strip(), e.trust.strip(), e.status, e.node_uid, eid, pid),
        )
        row = c.execute("SELECT * FROM evidence WHERE id=?", (eid,)).fetchone()
        item = attach_evidence_no(c, pid, [dict(row)])[0]
    return item


@router.post("/{pid}/evidence/{eid}/acknowledge")
def acknowledge_evidence(pid: int, eid: int):
    """'근거 자료 변경됨' 신호를 사람이 확인해 내린다.
    자료를 다시 읽고 이 근거가 아직 유효한지 판단하는 것은 사람의 몫이므로,
    근거 항목을 수정하는 것만으로는 이 신호가 꺼지지 않는다."""
    with connect() as c:
        _require(c, pid)
        if not c.execute("SELECT id FROM evidence WHERE id=? AND project_id=?", (eid, pid)).fetchone():
            raise HTTPException(404, "근거 항목을 찾을 수 없습니다.")
        c.execute("UPDATE evidence SET source_changed=0 WHERE id=? AND project_id=?", (eid, pid))
        row = c.execute("SELECT * FROM evidence WHERE id=?", (eid,)).fetchone()
        item = attach_evidence_no(c, pid, [dict(row)])[0]
    return item


@router.delete("/{pid}/evidence/{eid}")
def delete_evidence(pid: int, eid: int):
    with connect() as c:
        _require(c, pid)
        c.execute("DELETE FROM evidence WHERE id=? AND project_id=?", (eid, pid))
    return {"deleted": eid}
