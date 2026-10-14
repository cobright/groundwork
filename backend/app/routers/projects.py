# -*- coding: utf-8 -*-
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect, now
from ..services.evidence import STATEMENT_KIND
from ..services.progress import fact_lines, progress_claims
from .dashboard import compute_metrics

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str | None = None
    doc_type: str | None = None
    purpose: str | None = None
    audience: str | None = None
    due_date: str | None = None


@router.get("")
def list_projects(archived: bool = False):
    """기본은 활성 업무만. archived=true 면 보관함(캐비넷)에 든 업무만."""
    with connect() as c:
        if archived:
            rows = c.execute(
                "SELECT * FROM projects WHERE archived_at<>'' ORDER BY archived_at DESC, id DESC").fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM projects WHERE archived_at='' ORDER BY updated_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_project(p: ProjectIn):
    ts = now()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO projects(name,doc_type,purpose,audience,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            ((p.name or "").strip(), (p.doc_type or "").strip(), (p.purpose or "").strip(),
             (p.audience or "").strip(), (p.due_date or "").strip(), ts, ts),
        )
        row = c.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.put("/{pid}")
def update_project(pid: int, p: ProjectIn):
    """전달된 필드만 갱신(부분 수정). 보내지 않은 필드는 건드리지 않는다."""
    with connect() as c:
        cur = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not cur:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        vals = {
            "name": p.name.strip() if p.name is not None else cur["name"],
            "doc_type": p.doc_type.strip() if p.doc_type is not None else cur["doc_type"],
            "purpose": p.purpose.strip() if p.purpose is not None else cur["purpose"],
            "audience": p.audience.strip() if p.audience is not None else cur["audience"],
            "due_date": p.due_date.strip() if p.due_date is not None else cur["due_date"],
        }
        c.execute("UPDATE projects SET name=?, doc_type=?, purpose=?, audience=?, due_date=?, updated_at=? WHERE id=?",
                  (vals["name"], vals["doc_type"], vals["purpose"], vals["audience"], vals["due_date"], now(), pid))
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return dict(row)


@router.get("/{pid}")
def get_project(pid: int):
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "업무를 찾을 수 없습니다.")
    return dict(row)


# ────────────── 보관함(캐비넷) ──────────────
# 지워야 할지는 모르겠으나 지금 관리 대상은 아닌 업무를 넣어두는 곳.
# 삭제는 이 안에서만 할 수 있다 → 활성 업무는 실수로 지워지지 않는다.

class ArchiveIn(BaseModel):
    note: str | None = None      # 왜 보관하는지 한 줄(선택)


def _counts(c, pid: int) -> dict:
    """이 업무를 지우면 함께 사라지는 것들의 건수."""
    one = lambda sql: c.execute(sql, (pid,)).fetchone()["n"]
    return {
        "outline": one("SELECT COUNT(*) n FROM outline_nodes WHERE project_id=?"),
        "resources": one("SELECT COUNT(*) n FROM resources WHERE project_id=?"),
        "evidence": one("SELECT COUNT(*) n FROM evidence WHERE project_id=?"),
        "drafts": one("SELECT COUNT(*) n FROM drafts WHERE project_id=? AND body<>''"),
        "opinions": one("SELECT COUNT(*) n FROM review_opinions WHERE project_id=?"),
        "requests": one("SELECT COUNT(*) n FROM data_requests WHERE project_id=?"),
        "surveys": one("SELECT COUNT(*) n FROM surveys WHERE project_id=?"),
        # 공통자료실 자료는 project_id 가 NULL 이라 삭제되지 않는다(참조만 끊긴다).
        "library_refs": one("SELECT COUNT(*) n FROM resource_refs WHERE project_id=?"),
    }


@router.post("/{pid}/archive")
def archive_project(pid: int, body: ArchiveIn):
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        if row["archived_at"]:
            raise HTTPException(400, "이미 보관함에 있는 업무입니다.")
        c.execute("UPDATE projects SET archived_at=?, archive_note=? WHERE id=?",
                  (now(), (body.note or "").strip(), pid))
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return dict(row)


@router.post("/{pid}/unarchive")
def unarchive_project(pid: int):
    """보관함에서 꺼내 다시 진행 중인 업무로 되돌린다."""
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        c.execute("UPDATE projects SET archived_at='', archive_note='', updated_at=? WHERE id=?", (now(), pid))
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return dict(row)


@router.get("/{pid}/delete-preview")
def delete_preview(pid: int):
    """삭제하면 무엇이 사라지는지 미리 보여준다(삭제하지 않는다)."""
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        counts = _counts(c, pid)
    return {"name": row["name"], "archived": bool(row["archived_at"]), "counts": counts}


@router.delete("/{pid}")
def delete_project(pid: int):
    """보관함에 든 업무만 삭제할 수 있다. 되돌릴 수 없다."""
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        if not row["archived_at"]:
            raise HTTPException(409, "진행 중인 업무는 바로 삭제할 수 없습니다. 먼저 보관함에 넣은 뒤 삭제하세요.")
        counts = _counts(c, pid)
        # 자식 정리는 FK CASCADE 가 한다(connect() 가 PRAGMA foreign_keys=ON).
        # 공통자료실 자료는 project_id 가 NULL 이라 남고, 참조(resource_refs)만 끊긴다.
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"deleted": pid, "name": row["name"], "counts": counts}


# ────────────── 보고전 뽑기(spinoff) ──────────────
# 왜 별도 업무인가:
#   보고전은 계획서의 '한 부분'이 아니라 **다른 문서**다. 같은 업무의 목차를 보고전 틀로
#   갈아끼우면 계획서의 목차·집필카드·본문이 사라지고 근거·검토의 목차 연결이 끊긴다.
#   실제로 그 사고가 있었다(v0.19). 그래서 진행 중인 업무는 손대지 않고 새 업무를 만든다.
#
# 무엇을 가져오는가:
#   확정된 근거만 가져온다. 같은 resource_id 를 가리키므로 자료가 바뀌면 양쪽 모두에
#   source_changed 신호가 뜬다(원본을 복사하지 않는다 — 원칙 2).
#   목차 연결(node_uid)은 비워 둔다. 어느 항목에 쓸지는 사람이 정한다.

class SpinoffIn(BaseModel):
    doc_type: str                      # 어떤 보고전 틀로 뽑을지
    name: str | None = None            # 새 업무명(비우면 자동)
    carry_evidence: bool = True        # 확정 근거를 가져올지
    carry_progress: bool = True        # 원본 업무의 진행상황을 근거로 함께 넣을지


@router.post("/{pid}/spinoff", status_code=201)
def spinoff_project(pid: int, body: SpinoffIn):
    import uuid
    from ..services.templates import DOC_TEMPLATES

    tpl = DOC_TEMPLATES.get(body.doc_type)
    if not tpl:
        raise HTTPException(400, f"모르는 문서 유형입니다: {body.doc_type}")

    ts = now()
    with connect() as c:
        src = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not src:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")

        # 이름: '폐교 활용 — 상황 보고'  (유형명 앞의 '보고전 · ' 는 떼고 쓴다)
        short = body.doc_type.split("·")[-1].strip() or body.doc_type
        name = (body.name or "").strip() or f"{src['name']} — {short}"
        cur = c.execute(
            "INSERT INTO projects(name,doc_type,purpose,audience,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (name, body.doc_type, src["purpose"], src["audience"], ts, ts),
        )
        new_id = cur.lastrowid

        # 목차 + 집필카드를 틀에서 심는다
        sort = [0]

        def plant(nodes, parent=None):
            for n in nodes:
                uid = uuid.uuid4().hex[:12]
                sort[0] += 1
                c.execute(
                    "INSERT INTO outline_nodes(project_id,uid,parent_uid,sort,title) VALUES(?,?,?,?,?)",
                    (new_id, uid, parent, sort[0], n["title"]),
                )
                card = n.get("card")
                if card:
                    c.execute(
                        "INSERT INTO writing_cards(project_id,node_uid,purpose,question,message,content,length,status)"
                        " VALUES(?,?,?,?,?,?,?,?)",
                        (new_id, uid, card.get("purpose", ""), card.get("question", ""),
                         card.get("message", ""), card.get("content", ""),
                         card.get("length", "1쪽"), card.get("status", "작성 전")),
                    )
                plant(n["children"], uid)

        plant(tpl["nodes"])

        carried = 0
        if body.carry_evidence:
            # 확정된 자료에 붙은 근거만. 미확정 근거를 옮기면 '확정 전엔 근거가 아니다'가 무너진다.
            rows = c.execute(
                "SELECT e.* FROM evidence e "
                "JOIN resource_analysis a ON a.resource_id=e.resource_id "
                "WHERE e.project_id=? AND a.state='사용자 확정' ORDER BY e.id", (pid,)).fetchall()
            for e in rows:
                c.execute(
                    "INSERT INTO evidence(project_id,claim,resource_id,locator,trust,status,node_uid,"
                    "source_changed,created_at) VALUES(?,?,?,?,?,?,NULL,?,?)",
                    (new_id, e["claim"], e["resource_id"], e["locator"], e["trust"], e["status"],
                     e["source_changed"], ts),
                )
                # 새 업무에서도 그 자료를 볼 수 있도록 참조를 건다(원본은 옮기지 않는다).
                c.execute("INSERT OR IGNORE INTO resource_refs(project_id,resource_id,created_at) VALUES(?,?,?)",
                          (new_id, e["resource_id"], ts))
                carried += 1

        # 진행상황을 근거로 함께 넣는다.
        #
        # 왜 '담당자 진술' 자리인가: 전부 DB 를 센 결과라 지어낸 것은 하나도 없지만,
        # **문서로 확인된 자료는 아니다.** 진술과 같은 자리에 두어야 `[진술]` 표시가
        # 초고·검토·최종본까지 그대로 따라간다(services/evidence.evidence_mark).
        #
        # 왜 바로 '사용자 확정'인가: 담당자 진술의 채택과 같다 — 사람이 이 상자를 켜고
        # ‘뽑기’를 누른 행위가 곧 채택이다. 상황 보고는 이 사실들이 곧 재료이므로,
        # 여기서 한 번 더 확정을 요구하면 '빠른 길'이라는 명분이 사라진다.
        progress = 0
        if body.carry_progress:
            m = compute_metrics(c, src)
            claims = progress_claims(m, src["name"])
            if claims:
                today = ts[:10]
                text = "\n".join(fact_lines(m)) + f"\n\n(‘{src['name']}’의 {today} 기준 진행상황을 프로그램이 센 것입니다.)"
                author = c.execute("SELECT value FROM settings WHERE key='author_name'").fetchone()
                cur = c.execute(
                    "INSERT INTO resources(project_id,name,kind,source_org,base_date,trust,text,note,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (new_id, f"‘{src['name']}’ 진행상황 ({today})", STATEMENT_KIND,
                     (author["value"] if author else "") or "워크벤치", today, "진술", text, "", ts))
                rid = cur.lastrowid
                c.execute(
                    "INSERT INTO resource_analysis(resource_id,summary,key_points,usable_for,cautions,"
                    "state,model,analyzed_at) VALUES(?,?,?,?,?,?,?,?)",
                    (rid, text, json.dumps(claims, ensure_ascii=False), "[]",
                     json.dumps(["프로그램이 센 진행 사실이며 문서로 확인된 자료가 아님"], ensure_ascii=False),
                     "사용자 확정", "(진행상황 자동 정리)", ts))
                for claim in claims:
                    c.execute(
                        "INSERT INTO evidence(project_id,claim,resource_id,locator,trust,status,node_uid,created_at) "
                        "VALUES(?,?,?,?,?,?,NULL,?)",
                        (new_id, claim, rid, "", "진술", "진술", ts))
                    progress += 1

        row = c.execute("SELECT * FROM projects WHERE id=?", (new_id,)).fetchone()
        nodes = c.execute("SELECT COUNT(*) n FROM outline_nodes WHERE project_id=?", (new_id,)).fetchone()["n"]
    d = dict(row)
    d["created_nodes"] = nodes
    d["carried_evidence"] = carried
    d["carried_progress"] = progress
    d["source_name"] = src["name"]
    return d
