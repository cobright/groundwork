# -*- coding: utf-8 -*-
import re
import io
import urllib.parse
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from ..db import connect, now
from ..services.attachments import MAX_BYTES, read_upload, store_file
from ..services.doc_read import ReadError
from ..services.numbering import number_map

router = APIRouter(prefix="/api/projects", tags=["requests"])

STATUSES = ["필요", "요청함", "회신옴", "반영", "보류"]
_NEED_RE = re.compile(r"\[확인\s*필요(?::\s*([^\]]*))?\]")


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _row(c, r, number, title):
    d = dict(r)
    d["node_number"] = number.get(r["node_uid"], "") if r["node_uid"] else ""
    d["node_title"] = title.get(r["node_uid"], "") if r["node_uid"] else ""
    if r["dept_id"]:
        dep = c.execute("SELECT name FROM departments WHERE id=?", (r["dept_id"],)).fetchone()
        d["dept_name"] = dep["name"] if dep else ""
    else:
        d["dept_name"] = ""
    # 회신자료 이름과, 파일로 받았다면 그 파일 이름(원본을 다시 열 수 있게).
    #
    # 자료를 지우면 이 열에 없는 id 가 남는다(자료 삭제가 요청 대장까지 건드리지는 않는다).
    # 예전엔 그 상태를 '등록됨: (삭제된 자료)' 로만 보여줘서 다시 등록할 길이 막혔다.
    # 지워진 것은 등록되지 않은 것과 같으므로 **없던 일로 돌려주고**, 다만 사라졌다는 사실은
    # 따로 알린다(담당자가 "내가 지웠구나"를 알아야 다시 올릴지 판단한다).
    d["received_resource_name"] = ""
    d["received_filename"] = ""
    d["received_memo"] = ""          # 회신자료의 담당자 메모(자료·근거의 그 칸과 같은 칸)
    d["received_lost"] = False
    if r["received_resource_id"]:
        rr = c.execute("SELECT name, note FROM resources WHERE id=?", (r["received_resource_id"],)).fetchone()
        if rr:
            d["received_resource_name"] = rr["name"]
            d["received_memo"] = rr["note"] or ""
            f = c.execute("SELECT filename FROM resource_files WHERE resource_id=?",
                          (r["received_resource_id"],)).fetchone()
            d["received_filename"] = f["filename"] if f else ""
        else:
            d["received_resource_id"] = None
            d["received_lost"] = True
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
        number, title = number_map(c, pid)
        rows = c.execute("SELECT * FROM data_requests WHERE project_id=? ORDER BY id", (pid,)).fetchall()
        out = [_row(c, r, number, title) for r in rows]
    return out


@router.post("/{pid}/requests/collect")
def collect_requests(pid: int):
    """흩어진 '필요한 자료' 신호를 모은다.
    - 초고 본문의 [확인 필요: ...]
    - 검토의견의 '필요조치'(needs)
    이미 수집된 것(origin_ref 중복)은 건너뛴다 — 상태를 바꾼 항목이 '필요'로 되돌아가지 않는다.
    다만 목록에서 아예 지운 항목은 흔적이 남지 않으므로 다시 수집된다."""
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
        number, title = number_map(c, pid)
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
        number, title = number_map(c, pid)
        row = c.execute("SELECT * FROM data_requests WHERE id=?", (rid,)).fetchone()
        item = _row(c, row, number, title)
    return item


def _pick_request(c, pid: int, rid: int):
    """회신을 붙일 요청 항목을 찾는다. 이미 회신자료가 있으면 막는다(한 항목에 하나)."""
    r = c.execute("SELECT * FROM data_requests WHERE id=? AND project_id=?", (rid, pid)).fetchone()
    if not r:
        raise HTTPException(404, "요청 항목을 찾을 수 없습니다.")
    if r["received_resource_id"]:
        if c.execute("SELECT id FROM resources WHERE id=?", (r["received_resource_id"],)).fetchone():
            raise HTTPException(400, "이미 이 항목의 회신자료가 등록되어 있습니다.")
    return r


def _link_received(c, pid: int, r, name: str, text: str) -> int:
    """회신 내용을 이 업무의 자료로 만들고 요청 항목에 잇는다.
    자료명은 요청 내용, 작성기관은 요청한 부서 — 나중에 근거표에서 '어디서 온 수치인가'가 보인다."""
    dep = c.execute("SELECT name FROM departments WHERE id=?", (r["dept_id"],)).fetchone() if r["dept_id"] else None
    cur = c.execute(
        "INSERT INTO resources(project_id,name,kind,source_org,base_date,trust,text,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (pid, name[:120] or "회신자료", "부서자료", dep["name"] if dep else "", "", "보통", text, now()))
    new_rid = cur.lastrowid
    c.execute("UPDATE data_requests SET received_resource_id=?, "
              "status=CASE WHEN status IN ('필요','요청함') THEN '회신옴' ELSE status END WHERE id=?",
              (new_rid, r["id"]))
    return new_rid


def _request_item(c, pid: int, rid: int):
    number, title = number_map(c, pid)
    row = c.execute("SELECT * FROM data_requests WHERE id=?", (rid,)).fetchone()
    return _row(c, row, number, title)


@router.post("/{pid}/requests/{rid}/register-resource")
def register_received_resource(pid: int, rid: int):
    """회신받은 자료를 이 업무의 자료로 등록한다(적어 둔 메모를 본문으로).
    이후 사용자가 자료·근거 화면에서 분석·근거 연결을 이어간다."""
    with connect() as c:
        _require(c, pid)
        r = _pick_request(c, pid, rid)
        new_rid = _link_received(c, pid, r, r["need"][:80], r["received_note"] or "")
        item = _request_item(c, pid, rid)
    return {"resource_id": new_rid, "request": item}


@router.post("/{pid}/requests/{rid}/received-file", status_code=201)
async def register_received_file(pid: int, rid: int, request: Request, filename: str = ""):
    """부서가 보낸 **파일 그대로** 회신 등록한다(엑셀·한글·워드·PDF).

    왜 필요한가: 부서 회신은 대개 파일로 온다. 지금까지는 담당자가 그 파일을 열어
    직접 읽고 요약해 붙여넣어야 했는데, 세부사업계획서·추진상황보고를 매 건 그렇게
    살피는 것은 실제로는 불가능하다. 여기가 AI 가 필요한 자리다.

    다만 이 입구는 **읽어서 담기까지만** 한다. 분석은 자료·근거 화면에서 사람이 누른다.
    그때 '무엇을 요청했는지'가 함께 넘어가, 요청한 것 중 빠진 것을 짚어 준다.
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
        r = _pick_request(c, pid, rid)
        new_rid = _link_received(c, pid, r, r["need"][:80] or filename, info["text"])
        store_file(c, new_rid, data, filename, info)
        # 회신 메모(received_note)는 건드리지 않는다. 그 칸은 사람이 적는 자리이고,
        # 어떤 파일로 받았는지는 received_filename 으로 따로 보여준다.
        item = _request_item(c, pid, rid)
    return {"resource_id": new_rid, "request": item, "file_kind": info["file_kind"],
            "chars": len(info["text"]), "read_note": info["read_note"]}


@router.delete("/{pid}/requests/{rid}")
def delete_request(pid: int, rid: int):
    with connect() as c:
        _require(c, pid)
        c.execute("DELETE FROM data_requests WHERE id=? AND project_id=?", (rid, pid))
    return {"deleted": rid}


_SHEET_BAD = set(r'[]:*?/\\')


def _sheet_title(name: str, used: set) -> str:
    """엑셀 시트명 규칙에 맞춘다: 금지문자 제거, 31자 이내, 중복이면 번호를 붙인다.
    부서명에 '기획/예산' 처럼 슬래시가 들어가면 create_sheet 가 예외로 죽었다."""
    base = "".join(" " if ch in _SHEET_BAD else ch for ch in (name or "")).strip()[:31] or "부서"
    title = base
    n = 2
    while title in used:
        suffix = f"({n})"
        title = base[:31 - len(suffix)] + suffix
        n += 1
    used.add(title)
    return title


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
        number, title = number_map(c, pid)
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
    headers = ["연번", "관련 목차", "필요한 자료", "요청일", "회신 마감일", "상태", "비고"]
    widths = [6, 20, 46, 14, 12, 9, 26]

    order = sorted(groups.keys(), key=lambda k: (k == "미배정 부서", k))
    used_titles = set()
    for dept in order:
        ws = wb.create_sheet(title=_sheet_title(dept, used_titles))
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
