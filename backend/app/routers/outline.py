# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect, now
from ..skills.draft_writing import write_draft

router = APIRouter(prefix="/api/projects", tags=["outline"])


class Node(BaseModel):
    uid: str
    parent_uid: str | None = None
    sort: int = 0
    title: str = ""


class OutlineIn(BaseModel):
    nodes: list[Node]


class CardIn(BaseModel):
    purpose: str = ""
    question: str = ""
    message: str = ""
    content: str = ""
    length: str = "1쪽"
    status: str = "작성 전"


def _require_project(c, pid: int):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


@router.get("/{pid}/outline")
def get_outline(pid: int):
    with connect() as c:
        _require_project(c, pid)
        nodes = c.execute(
            "SELECT uid,parent_uid,sort,title FROM outline_nodes WHERE project_id=? ORDER BY sort", (pid,)
        ).fetchall()
        cards = c.execute("SELECT * FROM writing_cards WHERE project_id=?", (pid,)).fetchall()
    card_map = {}
    for r in cards:
        d = dict(r); d.pop("project_id"); uid = d.pop("node_uid")
        card_map[uid] = d
    return {"nodes": [dict(n) for n in nodes], "cards": card_map}


@router.put("/{pid}/outline")
def put_outline(pid: int, body: OutlineIn):
    keep = {n.uid for n in body.nodes}
    with connect() as c:
        _require_project(c, pid)
        # 목차 항목만 통째로 교체한다.
        c.execute("DELETE FROM outline_nodes WHERE project_id=?", (pid,))
        for i, n in enumerate(body.nodes):
            c.execute(
                "INSERT INTO outline_nodes(project_id,uid,parent_uid,sort,title) VALUES(?,?,?,?,?)",
                (pid, n.uid, n.parent_uid, n.sort if n.sort is not None else i, n.title),
            )
        # ★ 카드 보존: 사라진 항목의 카드만 정리하고, 나머지 카드는 건드리지 않는다.
        existing = [r["node_uid"] for r in c.execute(
            "SELECT node_uid FROM writing_cards WHERE project_id=?", (pid,)).fetchall()]
        for uid in existing:
            if uid not in keep:
                c.execute("DELETE FROM writing_cards WHERE project_id=? AND node_uid=?", (pid, uid))
        c.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
    return {"saved": len(body.nodes)}


@router.put("/{pid}/cards/{uid}")
def put_card(pid: int, uid: str, card: CardIn):
    with connect() as c:
        _require_project(c, pid)
        c.execute(
            """INSERT INTO writing_cards(project_id,node_uid,purpose,question,message,content,length,status)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(project_id,node_uid) DO UPDATE SET
                 purpose=excluded.purpose, question=excluded.question, message=excluded.message,
                 content=excluded.content, length=excluded.length, status=excluded.status""",
            (pid, uid, card.purpose, card.question, card.message, card.content, card.length, card.status),
        )
    return {"saved": uid}


# ────────────── 초고(draft) ──────────────
class DraftGenIn(BaseModel):
    strictness: str = "엄격"          # 엄격/유연/자료목록
    provider: str | None = None


class DraftBodyIn(BaseModel):
    body: str = ""


def _card_dict(c, pid, uid):
    r = c.execute("SELECT * FROM writing_cards WHERE project_id=? AND node_uid=?", (pid, uid)).fetchone()
    return dict(r) if r else {}


def _linked_evidence(c, pid, uid):
    """이 목차(uid)에 연결된 근거 + 근거자료 요약/확정상태를 함께 모은다."""
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
    # 번호 계산
    children = {}
    for n in nodes:
        children.setdefault(n["parent_uid"], []).append(n)
    for a in children.values():
        a.sort(key=lambda x: x["sort"])
    number = {}
    def walk(parent, prefix):
        for i, n in enumerate(children.get(parent, [])):
            num = f"{prefix}{i+1}"
            number[n["uid"]] = num
            walk(n["uid"], num + ".")
    walk(None, "")
    return title, number.get(uid, "")


@router.get("/{pid}/nodes/{uid}/draft")
def get_draft(pid: int, uid: str):
    with connect() as c:
        _require_project(c, pid)
        d = c.execute("SELECT * FROM drafts WHERE project_id=? AND node_uid=?", (pid, uid)).fetchone()
        card = _card_dict(c, pid, uid)
        ev = _linked_evidence(c, pid, uid)
        title, number = _title_and_number(c, pid, uid)
    confirmed = [e for e in ev if e.get("state") == "사용자 확정"]
    return {
        "draft": dict(d) if d else {"body": "", "ai_suggestion": "", "strictness": "엄격"},
        "title": title, "number": number,
        "card": card,
        "evidence_count": len(ev), "confirmed_count": len(confirmed),
    }


@router.post("/{pid}/nodes/{uid}/draft/generate")
def generate_draft(pid: int, uid: str, body: DraftGenIn):
    with connect() as c:
        _require_project(c, pid)
        if not c.execute("SELECT 1 FROM outline_nodes WHERE project_id=? AND uid=?", (pid, uid)).fetchone():
            raise HTTPException(404, "목차 항목을 찾을 수 없습니다.")
        card = _card_dict(c, pid, uid)
        ev = _linked_evidence(c, pid, uid)
        title, number = _title_and_number(c, pid, uid)
    try:
        result = write_draft(card, ev, title, number, body.strictness, body.provider)
    except Exception as e:
        raise HTTPException(502, f"초고 생성 실패: {e}")
    with connect() as c:
        c.execute(
            """INSERT INTO drafts(project_id,node_uid,body,ai_suggestion,strictness,model,updated_at)
               VALUES(?,?,COALESCE((SELECT body FROM drafts WHERE project_id=? AND node_uid=?),''),?,?,?,?)
               ON CONFLICT(project_id,node_uid) DO UPDATE SET
                 ai_suggestion=excluded.ai_suggestion, strictness=excluded.strictness,
                 model=excluded.model, updated_at=excluded.updated_at""",
            (pid, uid, pid, uid, result["ai_suggestion"], result["strictness"], result["model"], now()),
        )
    return result


@router.put("/{pid}/nodes/{uid}/draft")
def save_draft_body(pid: int, uid: str, body: DraftBodyIn):
    """사용자가 반영한 최종 본문을 저장한다(AI 제안과 별개)."""
    with connect() as c:
        _require_project(c, pid)
        c.execute(
            """INSERT INTO drafts(project_id,node_uid,body,updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(project_id,node_uid) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at""",
            (pid, uid, body.body, now()),
        )
    return {"saved": uid}
