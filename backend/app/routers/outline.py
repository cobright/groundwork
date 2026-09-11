# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect, now
from ..skills.draft_writing import write_draft
from ..services.numbering import title_and_number
from ..services.evidence import linked_evidence
from ..services import snapshot
from ..services.templates import family_of

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
        # 사라지는 항목이 있으면 '직전' 상태를 적어 둔다 — 되돌아갈 자리(v0.19 사고).
        # 항목이 하나도 안 사라지는 저장(이름 고치기·순서 바꾸기·추가)은 잃을 것이 없으므로 찍지 않는다.
        # 매번 찍으면 글자 한 자 고칠 때마다 쌓여, 정작 필요한 스냅샷이 밀려난다.
        had = {r["uid"] for r in c.execute("SELECT uid FROM outline_nodes WHERE project_id=?", (pid,))}
        removed = had - keep
        if removed:
            snapshot.take(c, pid, f"목차 교체(항목 {len(removed)}개 사라짐)")
        # 목차 항목만 통째로 교체한다.
        c.execute("DELETE FROM outline_nodes WHERE project_id=?", (pid,))
        for i, n in enumerate(body.nodes):
            c.execute(
                "INSERT INTO outline_nodes(project_id,uid,parent_uid,sort,title) VALUES(?,?,?,?,?)",
                (pid, n.uid, n.parent_uid, n.sort if n.sort is not None else i, n.title),
            )
        # ★ 살아남은 항목의 카드·본문은 uid 에 묶여 그대로 따라온다(재정렬·개명해도 보존).
        #    사라진 항목만 정리한다: 카드와 본문을 '함께' 지운다.
        #    예전에는 카드만 지워 본문이 유령으로 남았고, 그 본문이 진행률에 계속 잡혔다.
        for table in ("writing_cards", "drafts"):
            gone = [r["node_uid"] for r in c.execute(
                f"SELECT node_uid FROM {table} WHERE project_id=?", (pid,)).fetchall() if r["node_uid"] not in keep]
            for uid in gone:
                c.execute(f"DELETE FROM {table} WHERE project_id=? AND node_uid=?", (pid, uid))
        # 검토의견은 '그 본문'에 대한 지적이다. 본문이 사라지면 의견도 가리킬 곳이 없다.
        # 남겨 두면 죽은 목차를 가리킨 채 검토 목록에 계속 떠서 진행 판단을 흐린다
        # (지워진 목차의 유령 본문과 같은 종류의 사고).
        gone_ops = [r["id"] for r in c.execute(
            "SELECT id, node_uid FROM review_opinions WHERE project_id=? AND node_uid IS NOT NULL",
            (pid,)).fetchall() if r["node_uid"] not in keep]
        for oid in gone_ops:
            c.execute("DELETE FROM review_opinions WHERE id=?", (oid,))
        # 근거·자료요청은 지우지 않는다(사람이 만든 기록) — 목차 연결만 끊는다.
        for table in ("evidence", "data_requests"):
            gone = [r["id"] for r in c.execute(
                f"SELECT id, node_uid FROM {table} WHERE project_id=? AND node_uid IS NOT NULL",
                (pid,)).fetchall() if r["node_uid"] not in keep]
            for rid in gone:
                c.execute(f"UPDATE {table} SET node_uid=NULL WHERE id=?", (rid,))
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


@router.get("/{pid}/nodes/{uid}/draft")
def get_draft(pid: int, uid: str):
    with connect() as c:
        _require_project(c, pid)
        d = c.execute("SELECT * FROM drafts WHERE project_id=? AND node_uid=?", (pid, uid)).fetchone()
        card = _card_dict(c, pid, uid)
        ev = linked_evidence(c, pid, uid)
        title, number = title_and_number(c, pid, uid)
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
        ev = linked_evidence(c, pid, uid)
        title, number = title_and_number(c, pid, uid)
        # 문서 유형이 문체를 가른다(계획서=서술 / 보고전=개조식·줄수 제한).
        dt = c.execute("SELECT doc_type FROM projects WHERE id=?", (pid,)).fetchone()["doc_type"]
    try:
        result = write_draft(card, ev, title, number, body.strictness, body.provider,
                             family=family_of(dt))
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


# ────────────── 되돌리기(목차 스냅샷) ──────────────
@router.get("/{pid}/outline/snapshots")
def list_snapshots(pid: int):
    """되돌아갈 수 있는 자리 목록. 원본(data)은 크므로 여기서는 빼고 요약만 준다."""
    with connect() as c:
        _require_project(c, pid)
        rows = c.execute(
            "SELECT id,taken_at,reason,summary FROM outline_snapshots WHERE project_id=? ORDER BY id DESC",
            (pid,)).fetchall()
    return [dict(r) for r in rows]


@router.post("/{pid}/outline/snapshots", status_code=201)
def take_snapshot(pid: int):
    """지금 상태를 직접 적어 둔다(큰 손질에 들어가기 전에 한 번)."""
    with connect() as c:
        _require_project(c, pid)
        sid = snapshot.take(c, pid, "직접 저장")
    if sid is None:
        raise HTTPException(400, "적어 둘 것이 없습니다(목차가 비어 있습니다).")
    return {"id": sid}


@router.post("/{pid}/outline/snapshots/{sid}/restore")
def restore_snapshot(pid: int, sid: int):
    """스냅샷 시점으로 되돌린다.

    되돌리기 직전 상태도 함께 적어 둔다 — **되돌리기를 되돌릴 수 있어야 한다.**
    (잘못 눌렀는데 돌아갈 자리가 없으면, 되돌리기가 새로운 사고가 된다.)
    """
    with connect() as c:
        _require_project(c, pid)
        snapshot.take(c, pid, "되돌리기 직전")
        out = snapshot.restore(c, pid, sid)
    if not out:
        raise HTTPException(404, "그 시점을 찾을 수 없습니다(오래되어 지워졌을 수 있습니다).")
    return out


@router.delete("/{pid}/outline/snapshots/{sid}")
def delete_snapshot(pid: int, sid: int):
    with connect() as c:
        _require_project(c, pid)
        c.execute("DELETE FROM outline_snapshots WHERE id=? AND project_id=?", (sid, pid))
    return {"deleted": sid}


@router.get("/{pid}/outline/replace-preview")
def replace_preview(pid: int):
    """목차를 통째로 갈아끼우면 무엇이 사라지는지 미리 보여준다(바꾸지 않는다).

    v0.19에 '계획서 업무에서 보고전 틀로 새로 채우기' 를 눌러 목차·집필카드·본문이
    사라지고 근거·검토의 목차 연결이 끊긴 사고가 있었다. 확인 문구가 카드와 본문만
    말하고 근거·검토는 말하지 않았던 것이 원인의 하나다. 사라지는 것을 전부 센다.
    """
    with connect() as c:
        _require_project(c, pid)
        one = lambda sql: c.execute(sql, (pid,)).fetchone()["n"]
        return {
            "nodes": one("SELECT COUNT(*) n FROM outline_nodes WHERE project_id=?"),
            "cards": one("SELECT COUNT(*) n FROM writing_cards WHERE project_id=?"),
            "bodies": one("SELECT COUNT(*) n FROM drafts WHERE project_id=? AND body<>''"),
            "opinions": one("SELECT COUNT(*) n FROM review_opinions WHERE project_id=? AND node_uid IS NOT NULL"),
            # 근거·자료요청은 지워지지 않는다 — 목차 연결만 끊긴다.
            "evidence_links": one("SELECT COUNT(*) n FROM evidence WHERE project_id=? AND node_uid IS NOT NULL"),
            "request_links": one("SELECT COUNT(*) n FROM data_requests WHERE project_id=? AND node_uid IS NOT NULL"),
        }
