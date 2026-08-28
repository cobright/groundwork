# -*- coding: utf-8 -*-
import re
import io
import urllib.parse
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from ..db import connect, now

router = APIRouter(prefix="/api/projects", tags=["requests"])

STATUSES = ["필요", "요청함", "회신옴", "반영", "보류"]
_NEED_RE = re.compile(r"\[확인\s*필요(?::\s*([^\]]*))?\]")


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _number_map(c, pid):
    nodes = c.execute("SELECT uid,parent_uid,sort,title FROM outline_nodes WHERE project_id=? ORDER BY sort", (pid,)).fetchall()
    children = {}
    for n in nodes:
        children.setdefault(n["parent_uid"], []).append(n)
    for a in children.values():
        a.sort(key=lambda x: x["sort"])
    number, title = {}, {}
    def walk(parent, prefix):
        for i, n in enumerate(children.get(parent, [])):
            num = f"{prefix}{i+1}"; number[n["uid"]] = num; title[n["uid"]] = n["title"]; walk(n["uid"], num + ".")
    walk(None, "")
    return number, title


def _row(c, r, number, title):
    d = dict(r)
    d["node_number"] = number.get(r["node_uid"], "") if r["node_uid"] else ""
    d["node_title"] = title.get(r["node_uid"], "") if r["node_uid"] else ""
    if r["dept_id"]:
        dep = c.execute("SELECT name FROM departments WHERE id=?", (r["dept_id"],)).fetchone()
        d["dept_name"] = dep["name"] if dep else ""
    else:
        d["dept_name"] = ""
    # 회신자료 이름
    d["received_resource_name"] = ""
    if r["received_resource_id"]:
        rr = c.execute("SELECT name FROM resources WHERE id=?", (r["received_resource_id"],)).fetchone()
        d["received_resource_name"] = rr["name"] if rr else "(삭제된 자료)"
    # 마감 초과 여부(회신 이전 상태에서만 의미)
    d["overdue"] = bool(r["due_date"]) and r["due_date"] < _today() and r["status"] in ("필요", "요청함")
    return d


def _today():
    from datetime import date
    return date.today().isoformat()


@router.get("/{pid}/requests")
def list_requests(pid: int):
    with connect() as c:
        _require(c, pid)
        number, title = _number_map(c, pid)
        rows = c.execute("SELECT * FROM data_requests WHERE project_id=? ORDER BY id", (pid,)).fetchall()
        out = [_row(c, r, number, title) for r in rows]
    return out


@router.post("/{pid}/requests/collect")
def collect_requests(pid: int):
    """흩어진 '필요한 자료' 신호를 모은다.
    - 초고 본문의 [확인 필요: ...]
    - 검토의견의 '필요조치'(needs)
    이미 수집된 것(origin_ref 중복)은 건너뛴다. 사용자가 처리한 항목도 되살리지 않는다."""
    created = 0
    with connect() as c:
        _require(c, pid)
        existing = {r["origin_ref"] for r in c.execute(
            "SELECT origin_ref FROM data_requests WHERE project_id=? AND origin_ref<>''", (pid,)).fetchall()}

        # 1) 초고 [확인 필요]
        drafts = c.execute("SELECT node_uid, body FROM drafts WHERE project_id=?", (pid,)).fetchall()
        for d in drafts:
            for m in _NEED_RE.finditer(d["body"] or ""):
                need = (m.group(1) or "").strip() or "(내용 미상)"
                ref = f"draft:{d['node_uid']}:{need}"
                if ref in existing:
                    continue
                c.execute(
                    "INSERT INTO data_requests(project_id,node_uid,need,status,origin,origin_ref,created_at) VALUES(?,?,?,?,?,?,?)",
                    (pid, d["node_uid"], need, "필요", "draft", ref, now()))
                existing.add(ref); created += 1

        # 2) 검토의견 필요조치
        ops = c.execute("SELECT id,node_uid,needs,problem,kind FROM review_opinions WHERE project_id=? AND needs<>''", (pid,)).fetchall()
        for o in ops:
            ref = f"op:{o['id']}"
            if ref in existing:
                continue
            need = o["needs"].strip()
            note = f"[{o['kind']}] {o['problem'][:60]}"
            c.execute(
                "INSERT INTO data_requests(project_id,node_uid,need,status,origin,origin_ref,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (pid, o["node_uid"], need, "필요", "review", ref, note, now()))
            existing.add(ref); created += 1
    return {"collected": created}


class RequestIn(BaseModel):
    need: str = ""
    node_uid: str | None = None
    dept_id: int | None = None
    status: str = "필요"
    note: str = ""


@router.post("/{pid}/requests", status_code=201)
def add_request(pid: int, body: RequestIn):
    with connect() as c:
        _require(c, pid)
        cur = c.execute(
            "INSERT INTO data_requests(project_id,node_uid,need,dept_id,status,origin,origin_ref,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (pid, body.node_uid, body.need.strip() or "(내용 미상)", body.dept_id, body.status, "user", "", body.note.strip(), now()))
        number, title = _number_map(c, pid)
        row = c.execute("SELECT * FROM data_requests WHERE id=?", (cur.lastrowid,)).fetchone()
        item = _row(c, row, number, title)
    return item


class RequestPatch(BaseModel):
    need: str | None = None
    node_uid: str | None = None
    dept_id: int | None = None
    status: str | None = None
    note: str | None = None
    requested_at: str | None = None
    due_date: str | None = None
    received_note: str | None = None
    clear_dept: bool = False


@router.put("/{pid}/requests/{rid}")
def update_request(pid: int, rid: int, patch: RequestPatch):
    with connect() as c:
        _require(c, pid)
        r = c.execute("SELECT * FROM data_requests WHERE id=? AND project_id=?", (rid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "요청 항목을 찾을 수 없습니다.")
        need = patch.need if patch.need is not None else r["need"]
        node_uid = patch.node_uid if patch.node_uid is not None else r["node_uid"]
        dept_id = None if patch.clear_dept else (patch.dept_id if patch.dept_id is not None else r["dept_id"])
        status = patch.status if patch.status is not None else r["status"]
        note = patch.note if patch.note is not None else r["note"]
        requested_at = patch.requested_at if patch.requested_at is not None else r["requested_at"]
        due_date = patch.due_date if patch.due_date is not None else r["due_date"]
        received_note = patch.received_note if patch.received_note is not None else r["received_note"]
        # 상태를 '요청함'으로 바꾸는데 요청일이 비어 있으면 오늘로 자동 기록
        if patch.status == "요청함" and not requested_at:
            requested_at = _today()
        c.execute(
            "UPDATE data_requests SET need=?, node_uid=?, dept_id=?, status=?, note=?, requested_at=?, due_date=?, received_note=? WHERE id=?",
            (need, node_uid, dept_id, status, note, requested_at, due_date, received_note, rid))
        number, title = _number_map(c, pid)
        row = c.execute("SELECT * FROM data_requests WHERE id=?", (rid,)).fetchone()
        item = _row(c, row, number, title)
    return item


@router.post("/{pid}/requests/{rid}/register-resource")
def register_received_resource(pid: int, rid: int):
    """회신받은 자료를 이 업무의 자료로 등록한다.
    요청 내용(need)을 자료명으로, 회신 메모(received_note)를 본문으로 하는 자료를 만들고
    요청 항목에 연결한다. 이후 사용자가 자료·근거 화면에서 분석·근거 연결을 이어간다."""
    with connect() as c:
        _require(c, pid)
        r = c.execute("SELECT * FROM data_requests WHERE id=? AND project_id=?", (rid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "요청 항목을 찾을 수 없습니다.")
        if r["received_resource_id"]:
            rr = c.execute("SELECT id FROM resources WHERE id=?", (r["received_resource_id"],)).fetchone()
            if rr:
                raise HTTPException(400, "이미 이 항목의 회신자료가 등록되어 있습니다.")
        cur = c.execute(
            "INSERT INTO resources(project_id,name,kind,source_org,base_date,trust,text,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (pid, r["need"][:80] or "회신자료", "부서자료", r["dept_id"] and (c.execute("SELECT name FROM departments WHERE id=?", (r["dept_id"],)).fetchone() or {"name": ""})["name"] or "",
             "", "보통", r["received_note"] or "", now()))
        new_rid = cur.lastrowid
        c.execute("UPDATE data_requests SET received_resource_id=?, status=CASE WHEN status IN ('필요','요청함') THEN '회신옴' ELSE status END WHERE id=?", (new_rid, rid))
        number, title = _number_map(c, pid)
        row = c.execute("SELECT * FROM data_requests WHERE id=?", (rid,)).fetchone()
        item = _row(c, row, number, title)
    return {"resource_id": new_rid, "request": item}


@router.delete("/{pid}/requests/{rid}")
def delete_request(pid: int, rid: int):
    with connect() as c:
        _require(c, pid)
        c.execute("DELETE FROM data_requests WHERE id=? AND project_id=?", (rid, pid))
    return {"deleted": rid}


@router.get("/{pid}/requests/export.xlsx")
def export_requests_xlsx(pid: int):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ModuleNotFoundError:
        raise HTTPException(500, "openpyxl 이 설치되지 않았습니다. 1_SETUP.bat 을 다시 실행해 주세요.")

    with connect() as c:
        proj = c.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
        if not proj:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        number, title = _number_map(c, pid)
        rows = [_row(c, r, number, title) for r in
                c.execute("SELECT * FROM data_requests WHERE project_id=? ORDER BY dept_id, id", (pid,)).fetchall()]

    # 부서별로 묶기(미배정은 '미배정 부서')
    groups = {}
    for r in rows:
        key = r["dept_name"] or "미배정 부서"
        groups.setdefault(key, []).append(r)

    wb = Workbook()
    wb.remove(wb.active)
    head_font = Font(name="맑은 고딕", bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2F5D62")
    cell_font = Font(name="맑은 고딕")
    thin = Side(style="thin", color="D0D4D8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    headers = ["연번", "관련 목차", "필요한 자료", "대상 부서 요청일", "회신 마감일", "상태", "비고"]
    widths = [6, 20, 46, 14, 12, 9, 26]

    order = sorted(groups.keys(), key=lambda k: (k == "미배정 부서", k))
    for dept in order:
        ws = wb.create_sheet(title=dept[:31])
        ws.append([f"[{proj['name']}] 자료요청서 — {dept}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.cell(1, 1).font = Font(name="맑은 고딕", bold=True, size=13)
        ws.append([])
        ws.append(headers)
        for i, h in enumerate(headers, 1):
            cell = ws.cell(ws.max_row, i); cell.font = head_font; cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center"); cell.border = border
        for idx, r in enumerate(groups[dept], 1):
            node = (r["node_number"] + " " + r["node_title"]).strip() if r["node_number"] else ""
            ws.append([idx, node, r["need"], r["requested_at"], r["due_date"], r["status"], r["note"]])
            for i in range(1, len(headers) + 1):
                cell = ws.cell(ws.max_row, i); cell.font = cell_font; cell.border = border
                cell.alignment = Alignment(vertical="top", wrap_text=(i in (2, 3, 7)))
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[chr(64 + i)].width = w

    if not groups:
        ws = wb.create_sheet(title="자료요청")
        ws.append(["수집된 요청 항목이 없습니다."])

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    safe = "".join(ch for ch in (proj["name"] or "자료요청서") if ch not in '\\/:*?"<>|').strip()[:40] or "자료요청서"
    filename = f"{safe}_자료요청서.xlsx"
    quoted = urllib.parse.quote(filename)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
