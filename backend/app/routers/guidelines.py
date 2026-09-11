# -*- coding: utf-8 -*-
"""공모 가이드라인 — 올리고, 분석하고, 사람이 골라 심는다.

세 단계로 나눈 이유(원칙 1: AI는 제안하고 사람이 확정한다):
  ① POST /guidelines            파일을 원본 그대로 담고, 읽어서 구간만 추정한다.
  ② POST /guidelines/{gid}/analyze   규칙 + LLM 으로 **제안만** 만든다. 아무것도 심지 않는다.
  ③ 채택                        목차는 프런트가 기존 '목차 틀 심기' 경로로,
                                자료는 POST /adopt-needs 로. 사람이 고른 것만 들어간다.

목차를 여기서 심지 않는 이유:
  분석 결과의 nodes 는 services/templates.py 의 틀과 **같은 모양**이다. 그래서
  프런트의 buildFromTemplate → PUT /outline 경로를 그대로 탄다. 파괴적 교체 앞에
  replace-preview 를 세워 둔 장치도 함께 물려받는다(v0.19 목차 유실 사고의 재발 방지).
  가이드라인은 새 파이프라인이 아니라 '그때그때 만들어지는 목차 틀'이다.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..db import connect, now
from ..services import formstore, gldiff
from ..services.doc_read import ReadError, read_document
from ..services.formstore import FormReject
from ..services.guideline import analyze_rules, guess_range, paths_of, to_tree
from ..services.hwpx_form import similarity
from ..skills.guideline_analysis import refine

router = APIRouter(prefix="/api", tags=["guidelines"])

MAX_BYTES = 40 * 1024 * 1024          # 가이드라인은 사진이 많아 양식보다 크다
DOC_KINDS = ("공고", "수립 가이드라인", "서식")
COLS = ("id,project_id,name,filename,doc_kind,size,file_kind,pages,blocks,read_note,"
        "range_start,range_end,analyzed_at,model,created_at")


def _require_project(c, pid: int):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _get(c, gid: int):
    row = c.execute("SELECT * FROM guidelines WHERE id=?", (gid,)).fetchone()
    if not row:
        raise HTTPException(404, "가이드라인을 찾을 수 없습니다.")
    return row


def _blocks_of(row) -> dict:
    """저장해 둔 원본을 다시 읽는다(원본을 그대로 갖고 있으므로 언제든 다시 읽을 수 있다)."""
    try:
        return read_document(row["data"], row["filename"])
    except ReadError as e:
        raise HTTPException(400, str(e))


# ────────────────────────── 보관 ──────────────────────────
@router.get("/projects/{pid}/guidelines")
def list_guidelines(pid: int):
    with connect() as c:
        _require_project(c, pid)
        rows = c.execute(f"SELECT {COLS} FROM guidelines WHERE project_id=? ORDER BY id DESC",
                         (pid,)).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects/{pid}/guidelines", status_code=201)
async def upload_guideline(pid: int, request: Request, filename: str = "",
                           name: str = "", doc_kind: str = "공고"):
    """파일을 원시 바이트로 받는다(본문 = 파일 그대로).

    multipart 를 쓰지 않는 이유는 forms.py 와 같다 — python-multipart 의존성이 늘면
    사용자가 1_SETUP 을 다시 돌려야 한다.
    """
    data = await request.body()
    if not data:
        raise HTTPException(400, "빈 파일입니다. 내려받기가 끊겼는지 확인해 주세요.")
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "파일이 너무 큽니다(40MB 이하).")
    try:
        doc = read_document(data, filename)
    except ReadError as e:
        raise HTTPException(400, str(e))

    rng = guess_range(doc["blocks"])
    fname = (filename or "").strip() or f"가이드라인.{doc['kind']}"
    label = (name or "").strip() or fname.rsplit(".", 1)[0]
    kind = doc_kind if doc_kind in DOC_KINDS else "공고"
    with connect() as c:
        _require_project(c, pid)
        cur = c.execute(
            "INSERT INTO guidelines(project_id,name,filename,doc_kind,data,size,file_kind,"
            "pages,blocks,read_note,range_start,range_end,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, label, fname, kind, data, len(data), doc["kind"], doc["pages"],
             len(doc["blocks"]), doc["note"], rng["start"], rng["end"], now()))
        row = c.execute(f"SELECT {COLS} FROM guidelines WHERE id=?", (cur.lastrowid,)).fetchone()
    out = dict(row)
    out["range_guessed"] = rng["guessed"]
    return out


@router.post("/guidelines/{gid}/to-form", status_code=201)
def guideline_to_form(gid: int):
    """가이드라인으로 올린 파일 중 **서식**을 양식 보관함으로 넘긴다.

    공모 한 건에는 공고·가이드라인과 함께 제출 서식이 딸려 온다. 그 서식은 최종본을
    채워 넣을 양식이기도 한데, 지금까지는 최종본 탭에서 **같은 파일을 한 번 더** 올려야 했다.
    원본은 이미 여기 있으므로 버튼 하나로 옮긴다(복사이며, 가이드라인 쪽은 그대로 남는다 —
    정정 공고 대비로 원본을 보관하는 것이 가이드라인 쪽의 일이기 때문).
    """
    with connect() as c:
        g = _get(c, gid)
        try:
            out = formstore.register(c, g["data"], g["filename"],
                                     name=g["name"] or g["filename"],
                                     note=f"공모 가이드라인({g['doc_kind']})에서 넘김")
        except FormReject as e:
            raise HTTPException(400, str(e))
    return out


@router.delete("/guidelines/{gid}")
def delete_guideline(gid: int):
    with connect() as c:
        _get(c, gid)
        c.execute("DELETE FROM guidelines WHERE id=?", (gid,))
    return {"deleted": gid}


# ────────────────────────── 범위 고르기 ──────────────────────────
@router.get("/guidelines/{gid}/blocks")
def get_blocks(gid: int, start: int = 0, limit: int = 400):
    """문서를 훑어 보며 '어디부터 어디까지가 목차·작성방법인가'를 고르게 한다.

    자동 추정은 기본값일 뿐이다. 조용히 틀린 구간을 잡고 아무도 모르는 것이
    가장 나쁘므로, 사람이 눈으로 보고 고칠 수 있어야 한다.
    """
    with connect() as c:
        row = _get(c, gid)
    doc = _blocks_of(row)
    blocks = doc["blocks"]
    window = [b for b in blocks if b["i"] >= start][:max(1, min(limit, 1000))]
    return {
        "file_kind": doc["kind"], "pages": doc["pages"], "total": len(blocks),
        "note": doc["note"],
        "range": {"start": row["range_start"], "end": row["range_end"]},
        "blocks": [{"i": b["i"], "page": b["page"], "kind": b["kind"],
                    "text": b["text"][:300]} for b in window],
    }


# ────────────────────────── 분석 ──────────────────────────
class AnalyzeIn(BaseModel):
    start: int | None = None
    end: int | None = None
    provider: str | None = None
    use_ai: bool = True


def _dept_hints(c, pid: int, needs: list[dict]) -> None:
    """예전에 비슷한 자료를 어느 부서에 요청했는지 찾아 붙인다(AI 없이).

    부서 이름은 기관마다 다르다. AI 가 맞힐 수 있는 것이 아니므로,
    이 업무에서 실제로 쌓인 기록을 근거로 제안한다.
    """
    past = c.execute(
        "SELECT r.need, d.name AS dept FROM data_requests r JOIN departments d ON d.id=r.dept_id "
        "WHERE r.dept_id IS NOT NULL").fetchall()
    if not past:
        return
    for n in needs:
        best, score = "", 0.0
        for p in past:
            s = similarity(n["need"], p["need"])
            if s > score:
                best, score = p["dept"], s
        if score >= 0.45 and not n.get("dept"):
            n["dept"] = best
            n["dept_why"] = f"예전에 비슷한 자료를 ‘{best}’에 요청했습니다(유사도 {score:.2f})"


@router.post("/guidelines/{gid}/analyze")
def analyze(gid: int, body: AnalyzeIn):
    """규칙으로 뽑고 LLM 으로 다듬는다. **제안만** 만든다 — 아무것도 심지 않는다."""
    with connect() as c:
        row = _get(c, gid)
        pid = row["project_id"]
        depts = [r["name"] for r in c.execute(
            "SELECT name FROM departments ORDER BY sort, id").fetchall()]
    doc = _blocks_of(row)
    blocks = doc["blocks"]
    lo = row["range_start"] if body.start is None else body.start
    hi = row["range_end"] if body.end is None else body.end
    if lo is None or lo < 0:
        lo = blocks[0]["i"]
    if hi is None or hi < 0:
        hi = blocks[-1]["i"]
    if lo > hi:
        raise HTTPException(400, "시작 위치가 끝보다 뒤입니다. 범위를 다시 골라주세요.")

    rules = analyze_rules(blocks, lo, hi)
    items = rules["outline"]["items"]
    if not items:
        raise HTTPException(400, "고른 범위에서 목차 항목을 찾지 못했습니다. "
                                 "범위를 넓히거나, 목차·작성방법이 있는 쪽으로 옮겨 보세요.")

    # LLM 에 보낼 뼈대 — 문서 전체가 아니라 항목과 후보만 보낸다.
    paths = paths_of(items)
    payload = [{"id": i, "path": paths[i],
                "instr": " ".join(it["instr"] + it["method"]),
                "cands": [n["text"] for n in it["needs"]]}
               for i, it in enumerate(items)]

    if body.use_ai:
        got = refine(payload, depts, body.provider)
    else:
        from ..skills.guideline_analysis import _fallback
        got = {"by_id": _fallback(payload), "model": "", "fallback": True,
               "reason": "AI 없이 규칙만으로 정리했습니다."}
    by_id = got["by_id"]

    # 자료 후보에 **출처**를 붙인다. 이것이 원칙 2 를 지키는 자리다 —
    # 담당자가 "이거 진짜 필요한 자료 맞나"를 원문에서 확인할 수 있어야 한다.
    needs_out: list[dict] = []
    for i, it in enumerate(items):
        cands = it["needs"]
        for n in (by_id.get(i, {}).get("needs") or []):
            src = cands[n["from"]] if 0 <= n.get("from", -1) < len(cands) else None
            needs_out.append({
                "ref": f"gl:{gid}:{i}:{len(needs_out)}",
                "need": n["need"], "why": n.get("why", ""),
                "dept": n.get("dept", ""), "dept_why": "",
                "node_index": i, "node_path": paths[i],
                "source": (src or {}).get("source", "지시문"),
                "src_block": (src or {}).get("block", it["block"]),
                "src_page": (src or {}).get("page", it["page"]),
                "src_text": (src or {}).get("text", "")[:200],
            })
    with connect() as c:
        _dept_hints(c, pid, needs_out)
        have = {r["name"]: r["id"] for r in c.execute("SELECT id,name FROM departments").fetchall()}
    for n in needs_out:
        n["dept_id"] = have.get(n["dept"])
        if n["dept"] and n["dept_id"] is None:      # 없는 부서 이름은 버린다(지어낸 것)
            n["dept"], n["dept_why"] = "", ""

    # 짝지어진 심사배점을 집필카드에 싣는다. 지금까지는 화면에서 보여만 주고
    # 초고까지 가지 않았다 — 배점은 '어느 항목에 분량을 쏟을지'를 정하는 정보다.
    by_node: dict[int, list[dict]] = {}
    for pr in rules["scoring_match"]["pairs"]:
        by_node.setdefault(pr["node_index"], []).append(pr)

    result = {
        "range": {"start": lo, "end": hi},
        "markers": rules["outline"]["markers"],
        "tree": to_tree(items, by_id, by_node),
        "node_paths": paths,
        "needs": needs_out,
        "scoring": rules["scoring"],
        "scoring_match": rules["scoring_match"],
        "basic": rules["basic"],
        "model": got["model"], "fallback": got["fallback"], "reason": got["reason"],
        "file_kind": doc["kind"], "read_note": doc["note"],
    }
    with connect() as c:
        c.execute("UPDATE guidelines SET range_start=?,range_end=?,analysis=?,analyzed_at=?,model=? "
                  "WHERE id=?",
                  (lo, hi, json.dumps(result, ensure_ascii=False), now(), got["model"], gid))
    return result


@router.get("/guidelines/{gid}/compare")
def compare_guidelines(gid: int, against: int | None = None):
    """이번 분석과 이전 분석을 견준다 — 정정 공고에서 무엇이 달라졌는가.

    `against` 를 비우면 **같은 업무에서 분석된 것 중 바로 앞엣것**을 고른다.
    다시 읽지 않고 저장된 분석 결과끼리 견준다(분석은 사람이 범위를 골라 확인한 것이므로,
    여기서 추측을 더 보태지 않는다).
    """
    with connect() as c:
        cur = _get(c, gid)
        if not cur["analysis"]:
            raise HTTPException(400, "이 파일은 아직 분석하지 않았습니다. 먼저 분석해 주세요.")
        if against is None:
            prev = c.execute(
                "SELECT id FROM guidelines WHERE project_id=? AND id<>? AND analysis<>'' "
                "ORDER BY id DESC LIMIT 1", (cur["project_id"], gid)).fetchone()
            if not prev:
                return {"available": False,
                        "reason": "견줄 이전 분석이 없습니다. 정정 공고를 올려 분석하면 그때 비교됩니다."}
            against = prev["id"]
        old = _get(c, against)
        if old["project_id"] != cur["project_id"]:
            raise HTTPException(400, "다른 업무의 가이드라인과는 견주지 않습니다.")
        if not old["analysis"]:
            raise HTTPException(400, "견줄 쪽이 아직 분석되지 않았습니다.")
    out = gldiff.compare(json.loads(old["analysis"]), json.loads(cur["analysis"]))
    out["available"] = True
    out["base"] = {"id": old["id"], "name": old["name"], "doc_kind": old["doc_kind"],
                   "analyzed_at": old["analyzed_at"]}
    out["target"] = {"id": cur["id"], "name": cur["name"], "doc_kind": cur["doc_kind"],
                     "analyzed_at": cur["analyzed_at"]}
    return out


@router.get("/guidelines/{gid}/analysis")
def get_analysis(gid: int):
    """마지막 분석 결과를 그대로 돌려준다(다시 열었을 때 처음부터 하지 않도록)."""
    with connect() as c:
        row = _get(c, gid)
    if not row["analysis"]:
        return {"analyzed": False}
    try:
        data = json.loads(row["analysis"])
    except json.JSONDecodeError:
        return {"analyzed": False}
    data["analyzed"] = True
    data["analyzed_at"] = row["analyzed_at"]
    return data


# ────────────────────────── 채택(자료) ──────────────────────────
class NeedIn(BaseModel):
    need: str
    why: str = ""
    dept_id: int | None = None
    node_uid: str | None = None
    ref: str = ""
    source: str = ""
    src_page: int = 0


class AdoptNeedsIn(BaseModel):
    items: list[NeedIn] = []


@router.post("/projects/{pid}/guidelines/{gid}/adopt-needs")
def adopt_needs(pid: int, gid: int, body: AdoptNeedsIn):
    """사람이 고른 자료만 자료요청 대장에 담는다.

    새 표를 만들지 않고 data_requests 를 그대로 쓴다 — 부서 배정·발송·마감·회신자료
    등록·xlsx 내보내기가 이미 다 붙어 있는 자리다. origin 만 'guideline' 으로 구분한다.
    """
    picked = [x for x in body.items if x.need.strip()]
    if not picked:
        raise HTTPException(400, "담을 자료를 하나 이상 고르세요.")
    created, skipped = 0, 0
    with connect() as c:
        _require_project(c, pid)
        _get(c, gid)
        existing = {r["origin_ref"] for r in c.execute(
            "SELECT origin_ref FROM data_requests WHERE project_id=? AND origin_ref<>''",
            (pid,)).fetchall()}
        for x in picked:
            ref = x.ref.strip() or f"gl:{gid}:{x.need.strip()[:40]}"
            if ref in existing:                     # 두 번 담기지 않는다
                skipped += 1
                continue
            note = x.why.strip()
            if x.source:
                where = f"{x.source}" + (f", {x.src_page}쪽" if x.src_page else "")
                note = (note + f" (가이드라인 {where})").strip()
            c.execute(
                "INSERT INTO data_requests(project_id,node_uid,need,dept_id,status,origin,"
                "origin_ref,note,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (pid, x.node_uid, x.need.strip(), x.dept_id, "필요", "guideline", ref,
                 note[:400], now()))
            existing.add(ref)
            created += 1
    return {"created": created, "skipped": skipped}
