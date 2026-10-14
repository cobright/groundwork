# -*- coding: utf-8 -*-
"""주민 설문: ①근거 지도 ②문항 설계 ③점검 ④폼으로 옮기기.

설계는 docs/design/survey.md. 이 라우터는 저장과 조립만 하고, 판단(점검·목표 응답 수·
폼 유형)은 services/survey.py 의 규칙이 한다. AI 를 부르지 않는다 — 뼈대가 AI 없이 끝까지 돈다.

⑤수집 ⑥정리 ⑦분석 ⑧확정은 **구글폼·네이버폼 실물 내보내기 파일을 받은 뒤** 만든다
(복수응답 구분자·척도 표기·기타 위치를 짐작으로 맞추면 실제 파일에서 깨진다 — 설계 문서 9장).
"""
import io
import json
import urllib.parse

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..db import connect, now
from ..services import survey as S
from ..services.numbering import number_map

router = APIRouter(prefix="/api", tags=["survey"])


class SurveyIn(BaseModel):
    title: str | None = None
    target: str | None = None
    method: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    population: int | None = None
    margin: float | None = None


class ClaimIn(BaseModel):
    node_uid: str | None = None
    claim: str | None = None
    basis: str | None = None
    note: str | None = None


class QuestionIn(BaseModel):
    text: str | None = None
    qtype: str | None = None
    options: list[str] | None = None
    required: bool | None = None
    other_allowed: bool | None = None
    rank_k: int | None = None
    profile: bool | None = None
    claim_id: int | None = None
    cross_with: list[int] | None = None
    branch: dict[str, int | str] | None = None
    note: str | None = None
    after_id: int | None = None          # 만들 때만: 이 문항 바로 뒤에 넣는다


class OrderIn(BaseModel):
    ids: list[int]


class ToRequestIn(BaseModel):
    need: str | None = None


# ────────────── 읽기 도우미 ──────────────
def _require_project(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _survey(c, sid) -> dict:
    r = c.execute("SELECT * FROM surveys WHERE id=?", (sid,)).fetchone()
    if not r:
        raise HTTPException(404, "설문을 찾을 수 없습니다(지워졌을 수 있습니다).")
    return dict(r)


def _q(r) -> dict:
    d = dict(r)
    d["options"] = S.loads(d["options"], [])
    d["cross_with"] = S.loads(d["cross_with"], [])
    d["branch"] = S.loads(d["branch"], {})
    for k in ("required", "other_allowed", "profile"):
        d[k] = bool(d[k])
    return d


def _questions(c, sid) -> list[dict]:
    return [_q(r) for r in c.execute(
        "SELECT * FROM survey_questions WHERE survey_id=? ORDER BY sort, id", (sid,))]


def _claims(c, sv) -> list[dict]:
    """근거 지도. 목차 순서대로(같은 항목 안에서는 만든 순서), 목차가 끊긴 주장은 끝에."""
    number, title = number_map(c, sv["project_id"])
    pos = {u: i for i, u in enumerate(number)}
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM survey_claims WHERE survey_id=? ORDER BY sort, id", (sv["id"],))]
    for r in rows:
        u = r["node_uid"]
        r["node_number"] = number.get(u, "") if u else ""
        r["node_title"] = title.get(u, "") if u else ""
        # 요청 대장에 이미 올렸는지(통계로 받칠 주장 → 자료요청)
        q = c.execute("SELECT id, status FROM data_requests WHERE project_id=? AND origin_ref=?",
                      (sv["project_id"], f"sv:{r['id']}")).fetchone()
        r["request_id"] = q["id"] if q else None
        r["request_status"] = q["status"] if q else ""
    rows.sort(key=lambda r: (pos.get(r["node_uid"], 10**6), r["sort"], r["id"]))
    return rows


def _full(c, sid) -> dict:
    sv = _survey(c, sid)
    claims = _claims(c, sv)
    qs = _questions(c, sid)
    rows = S.form_rows(qs)
    return {
        "survey": sv, "claims": claims, "questions": qs,
        "check": S.check(sv, claims, qs),
        "target_n": S.target_n(sv["population"], sv["margin"]),
        "form": rows, "checklist": S.checklist(sv, qs, rows),
    }


def _touch(c, sid):
    c.execute("UPDATE surveys SET updated_at=? WHERE id=?", (now(), sid))


# ────────────── 설문 ──────────────
@router.get("/projects/{pid}/surveys")
def list_surveys(pid: int):
    with connect() as c:
        _require_project(c, pid)
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM surveys WHERE project_id=? ORDER BY id", (pid,))]
        for r in rows:
            r["questions"] = c.execute("SELECT COUNT(*) n FROM survey_questions WHERE survey_id=?",
                                       (r["id"],)).fetchone()["n"]
            r["claims"] = c.execute("SELECT COUNT(*) n FROM survey_claims WHERE survey_id=?",
                                    (r["id"],)).fetchone()["n"]
    return rows


@router.post("/projects/{pid}/surveys", status_code=201)
def create_survey(pid: int, body: SurveyIn):
    with connect() as c:
        _require_project(c, pid)
        t = now()
        cur = c.execute(
            "INSERT INTO surveys(project_id,title,target,method,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (pid, (body.title or "").strip() or "주민 설문", (body.target or "").strip(),
             body.method if body.method in S.METHODS else "온라인 폼", t, t))
        return _full(c, cur.lastrowid)


@router.get("/surveys/{sid}")
def get_survey(sid: int):
    with connect() as c:
        return _full(c, sid)


@router.put("/surveys/{sid}")
def update_survey(sid: int, body: SurveyIn):
    """보낸 칸만 고친다(부분 수정)."""
    p = body.model_dump(exclude_unset=True)
    if "method" in p and p["method"] not in S.METHODS:
        raise HTTPException(400, f"조사 방식은 {', '.join(S.METHODS)} 중 하나입니다.")
    if p.get("population") is not None and p["population"] < 0:
        raise HTTPException(400, "대상 인구는 0 이상이어야 합니다.")
    if p.get("margin") is not None and not 0 < p["margin"] <= 20:
        raise HTTPException(400, "오차범위는 0보다 크고 20%p 이하로 적어 주세요.")
    with connect() as c:
        _survey(c, sid)
        for k, v in p.items():
            if v is None:
                continue
            c.execute(f"UPDATE surveys SET {k}=? WHERE id=?", (v.strip() if isinstance(v, str) else v, sid))
        _touch(c, sid)
        return _full(c, sid)


@router.get("/surveys/{sid}/delete-preview")
def delete_survey_preview(sid: int):
    """지우면 무엇이 사라지는지(지우지 않는다). 자료요청으로 넘긴 것은 요청 대장에 남는다."""
    with connect() as c:
        sv = _survey(c, sid)
        one = lambda sql: c.execute(sql, (sid,)).fetchone()["n"]
        return {
            "title": sv["title"],
            "claims": one("SELECT COUNT(*) n FROM survey_claims WHERE survey_id=?"),
            "questions": one("SELECT COUNT(*) n FROM survey_questions WHERE survey_id=?"),
        }


@router.delete("/surveys/{sid}")
def delete_survey(sid: int):
    with connect() as c:
        _survey(c, sid)
        c.execute("DELETE FROM surveys WHERE id=?", (sid,))     # 주장·문항은 CASCADE
    return {"deleted": sid}


# ────────────── ① 근거 지도 ──────────────
def _check_basis(b):
    if b is not None and b not in S.BASES:
        raise HTTPException(400, f"받칠 근거는 {', '.join(S.BASES)} 중 하나입니다.")


def _check_node(c, pid, uid):
    if uid and not c.execute("SELECT 1 FROM outline_nodes WHERE project_id=? AND uid=?", (pid, uid)).fetchone():
        raise HTTPException(400, "그 목차 항목이 없습니다(목차가 바뀌었을 수 있습니다). 화면을 새로 고쳐 주세요.")


@router.post("/surveys/{sid}/claims", status_code=201)
def add_claim(sid: int, body: ClaimIn):
    _check_basis(body.basis)
    with connect() as c:
        sv = _survey(c, sid)
        _check_node(c, sv["project_id"], body.node_uid)
        mx = c.execute("SELECT COALESCE(MAX(sort),0) m FROM survey_claims WHERE survey_id=?", (sid,)).fetchone()["m"]
        c.execute("INSERT INTO survey_claims(survey_id,project_id,node_uid,claim,basis,note,sort,created_at)"
                  " VALUES(?,?,?,?,?,?,?,?)",
                  (sid, sv["project_id"], body.node_uid or None, (body.claim or "").strip(),
                   body.basis or "미정", (body.note or "").strip(), mx + 1, now()))
        _touch(c, sid)
        return _full(c, sid)


@router.put("/surveys/{sid}/claims/{cid}")
def update_claim(sid: int, cid: int, body: ClaimIn):
    p = body.model_dump(exclude_unset=True)
    _check_basis(p.get("basis"))
    with connect() as c:
        sv = _survey(c, sid)
        if not c.execute("SELECT 1 FROM survey_claims WHERE id=? AND survey_id=?", (cid, sid)).fetchone():
            raise HTTPException(404, "그 주장을 찾을 수 없습니다.")
        if "node_uid" in p:
            _check_node(c, sv["project_id"], p["node_uid"])
            c.execute("UPDATE survey_claims SET node_uid=? WHERE id=?", (p["node_uid"] or None, cid))
        for k in ("claim", "basis", "note"):
            if p.get(k) is not None:
                c.execute(f"UPDATE survey_claims SET {k}=? WHERE id=?", (p[k].strip(), cid))
        _touch(c, sid)
        return _full(c, sid)


@router.delete("/surveys/{sid}/claims/{cid}")
def delete_claim(sid: int, cid: int):
    """주장을 지워도 문항은 남는다(연결만 끊긴다 — FK ON DELETE SET NULL). 끊긴 문항은 점검이 짚는다."""
    with connect() as c:
        _survey(c, sid)
        c.execute("DELETE FROM survey_claims WHERE id=? AND survey_id=?", (cid, sid))
        _touch(c, sid)
        return _full(c, sid)


@router.post("/surveys/{sid}/claims/{cid}/to-request")
def claim_to_request(sid: int, cid: int, body: ToRequestIn):
    """통계로 받칠 주장 → 부서 자료요청. 같은 주장을 두 번 올리지 않는다(origin_ref = sv:{주장 id})."""
    with connect() as c:
        sv = _survey(c, sid)
        cl = c.execute("SELECT * FROM survey_claims WHERE id=? AND survey_id=?", (cid, sid)).fetchone()
        if not cl:
            raise HTTPException(404, "그 주장을 찾을 수 없습니다.")
        ref = f"sv:{cid}"
        had = c.execute("SELECT id, status FROM data_requests WHERE project_id=? AND origin_ref=?",
                        (sv["project_id"], ref)).fetchone()
        if had:
            return {"request_id": had["id"], "status": had["status"], "already": True}
        need = (body.need or "").strip() or f"통계 자료: {cl['claim']}"
        cur = c.execute(
            "INSERT INTO data_requests(project_id,node_uid,need,status,origin,origin_ref,note,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (sv["project_id"], cl["node_uid"], need, "필요", "survey", ref,
             f"설문 ‘{sv['title']}’ 근거 지도에서", now()))
        return {"request_id": cur.lastrowid, "status": "필요", "already": False}


# ────────────── ② 문항 설계 ──────────────
def _clean_question(c, sid, p: dict) -> dict:
    if "qtype" in p and p["qtype"] not in S.QTYPES:
        raise HTTPException(400, f"문항 유형은 {', '.join(S.QTYPES)} 중 하나입니다.")
    if p.get("claim_id") is not None and not c.execute(
            "SELECT 1 FROM survey_claims WHERE id=? AND survey_id=?", (p["claim_id"], sid)).fetchone():
        raise HTTPException(400, "그 주장이 이 설문의 근거 지도에 없습니다.")
    if p.get("rank_k") is not None and not 1 <= p["rank_k"] <= 10:
        raise HTTPException(400, "순위는 1~10순위 사이로 정해 주세요.")
    if p.get("branch"):
        for v in p["branch"].values():
            if v != "end" and not isinstance(v, int):
                raise HTTPException(400, "분기 대상은 문항 번호 또는 '양식 제출'입니다.")
    out = {}
    for k, v in p.items():
        if k == "after_id":
            continue
        if k in ("options", "cross_with", "branch"):
            if k == "options" and v is not None:
                v = [str(o).strip() for o in v]
            v = json.dumps(v if v is not None else ([] if k != "branch" else {}), ensure_ascii=False)
        elif k in ("required", "other_allowed", "profile"):
            v = 1 if v else 0
        elif isinstance(v, str):
            v = v.strip()
        out[k] = v
    return out


@router.post("/surveys/{sid}/questions", status_code=201)
def add_question(sid: int, body: QuestionIn):
    p = body.model_dump(exclude_unset=True)
    with connect() as c:
        _survey(c, sid)
        vals = _clean_question(c, sid, p)
        ids = [r["id"] for r in c.execute(
            "SELECT id FROM survey_questions WHERE survey_id=? ORDER BY sort, id", (sid,))]
        cols = {"survey_id": sid, "created_at": now(), "sort": 0, **vals}
        cur = c.execute(f"INSERT INTO survey_questions({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                        list(cols.values()))
        new = cur.lastrowid
        at = ids.index(body.after_id) + 1 if body.after_id in ids else len(ids)
        ids.insert(at, new)
        for i, q in enumerate(ids):
            c.execute("UPDATE survey_questions SET sort=? WHERE id=?", (i + 1, q))
        _touch(c, sid)
        out = _full(c, sid)
        out["new_id"] = new
        return out


@router.put("/surveys/{sid}/questions/{qid}")
def update_question(sid: int, qid: int, body: QuestionIn):
    p = body.model_dump(exclude_unset=True)
    p.pop("after_id", None)
    with connect() as c:
        _survey(c, sid)
        if not c.execute("SELECT 1 FROM survey_questions WHERE id=? AND survey_id=?", (qid, sid)).fetchone():
            raise HTTPException(404, "그 문항을 찾을 수 없습니다.")
        vals = _clean_question(c, sid, p)
        for k, v in vals.items():
            c.execute(f"UPDATE survey_questions SET {k}=? WHERE id=?", (v, qid))
        _touch(c, sid)
        return _full(c, sid)


@router.delete("/surveys/{sid}/questions/{qid}")
def delete_question(sid: int, qid: int):
    """지운 문항을 가리키던 분석 계획·분기는 그대로 둔다 — 점검이 '지워진 문항을 가리킨다'고 짚어
    사람이 다시 고르게 한다(말없이 빼면 분석 계획이 줄어든 것을 아무도 모른다)."""
    with connect() as c:
        _survey(c, sid)
        c.execute("DELETE FROM survey_questions WHERE id=? AND survey_id=?", (qid, sid))
        _touch(c, sid)
        return _full(c, sid)


@router.put("/surveys/{sid}/questions-order")
def order_questions(sid: int, body: OrderIn):
    with connect() as c:
        _survey(c, sid)
        have = {r["id"] for r in c.execute("SELECT id FROM survey_questions WHERE survey_id=?", (sid,))}
        if set(body.ids) != have:
            raise HTTPException(409, "문항 목록이 바뀌었습니다. 화면을 새로 고친 뒤 다시 옮겨 주세요.")
        for i, q in enumerate(body.ids):
            c.execute("UPDATE survey_questions SET sort=? WHERE id=?", (i + 1, q))
        _touch(c, sid)
        return _full(c, sid)


# ────────────── ④ 폼으로 옮기기 ──────────────
@router.get("/surveys/{sid}/form.xlsx")
def export_form_xlsx(sid: int):
    """폼에 그대로 옮겨 적기 좋은 표. 폼을 API 로 만들지 않는다(계정 인증 · 행정망 — 원칙 4)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    except ModuleNotFoundError:
        raise HTTPException(500, "openpyxl 이 설치되지 않았습니다. 1_SETUP.bat 을 다시 실행해 주세요.")

    with connect() as c:
        full = _full(c, sid)
        sv = full["survey"]
        pname = c.execute("SELECT name FROM projects WHERE id=?", (sv["project_id"],)).fetchone()["name"]
        c.execute("UPDATE surveys SET exported_at=? WHERE id=?", (now(), sid))

    claims = {cl["id"]: cl for cl in full["claims"]}
    qnum = {r["id"]: r["no"] for r in full["form"]}
    qmap = {q["id"]: q for q in full["questions"]}

    wb = Workbook()
    head_font = Font(name="맑은 고딕", bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2F5D62")
    cell_font = Font(name="맑은 고딕")
    thin = Side(style="thin", color="D0D4D8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def sheet(ws, title, headers, widths, rows, wrap):
        ws.append([title])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.cell(1, 1).font = Font(name="맑은 고딕", bold=True, size=13)
        ws.append([])
        ws.append(headers)
        for i in range(1, len(headers) + 1):
            cell = ws.cell(ws.max_row, i)
            cell.font, cell.fill, cell.border = head_font, head_fill, border
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for r in rows:
            ws.append(r)
            for i in range(1, len(headers) + 1):
                cell = ws.cell(ws.max_row, i)
                cell.font, cell.border = cell_font, border
                cell.alignment = Alignment(vertical="top", wrap_text=i in wrap)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[chr(64 + i)].width = w

    ws = wb.active
    ws.title = "문항표"
    rows = []
    for r in full["form"]:
        q = qmap[r["id"]]
        cl = claims.get(q.get("claim_id"))
        claim = ""
        if cl:
            claim = (f"{cl['node_number']} " if cl["node_number"] else "") + cl["claim"]
        elif q.get("profile"):
            claim = "(응답자 특성)"
        cross = ", ".join(f"{qnum[x]}번" for x in q.get("cross_with") or [] if x in qnum)
        rows.append([r["no"], r["section"], r["text"], r["form_type"], "\n".join(r["options"]),
                     "필수" if r["required"] else "", "기타 추가" if r["other"] else "",
                     "\n".join(r["moves"]), claim, ("빈도 × " + cross) if cross else "빈도"])
    sheet(ws, f"[{pname}] {sv['title']} — 폼 옮기기 표",
          ["번호", "섹션", "문항", "폼 유형(구글폼)", "보기", "필수", "기타", "섹션 이동", "받치는 주장", "분석 계획"],
          [6, 6, 40, 30, 28, 7, 9, 26, 34, 16], rows, {3, 4, 5, 8, 9})

    ws2 = wb.create_sheet("폼 설정 점검표")
    sheet(ws2, "폼을 만든 뒤 설정에서 정할 것", ["확인", "항목", "설명"], [7, 24, 90],
          [["☐", it["item"], it["note"]] for it in full["checklist"]], {3})

    ws3 = wb.create_sheet("근거 지도")
    used = {}
    for q in full["questions"]:
        if q.get("claim_id"):
            used.setdefault(q["claim_id"], []).append(f"{qnum.get(q['id'], '?')}번")
    sheet(ws3, "계획서의 주장 ↔ 무엇으로 받치나", ["목차", "주장", "받칠 근거", "문항", "메모"], [24, 46, 10, 14, 30],
          [[(cl["node_number"] + " " + cl["node_title"]).strip() if cl["node_number"] else "(목차 연결 없음)",
            cl["claim"], cl["basis"], ", ".join(used.get(cl["id"], [])), cl["note"]] for cl in full["claims"]],
          {1, 2, 5})

    ws4 = wb.create_sheet("조사 개요")
    tn = full["target_n"]
    sheet(ws4, "조사 개요 — 결과를 인용할 때 숫자와 함께 다닌다", ["항목", "내용"], [18, 70], [
        ["조사명", sv["title"]], ["대상", sv["target"]], ["방식", sv["method"]],
        ["기간", f"{sv['period_from']} ~ {sv['period_to']}".strip(" ~")],
        ["대상 인구", f"{sv['population']:,}명" if sv["population"] else "(미정)"],
        ["목표 응답 수", f"{tn:,}명 (95% 신뢰수준, ±{sv['margin']:g}%p)" if tn and sv["population"] else
         (f"{tn:,}명 (대상 인구 미정 — 큰 모집단 기준)" if tn else "")],
    ], {2})

    buf = io.BytesIO()
    wb.save(buf)
    safe = "".join(ch for ch in (sv["title"] or "설문") if ch not in '\\/:*?"<>|').strip()[:40] or "설문"
    quoted = urllib.parse.quote(f"{safe}_폼옮기기표.xlsx")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
