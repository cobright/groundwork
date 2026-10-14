# -*- coding: utf-8 -*-
"""목차 스냅샷 — 통째로 갈아끼우기 '직전'의 상태를 적어 두고, 되돌린다.

왜 필요한가:
  v0.19에 진행 중이던 계획서의 목차 19개·집필카드 19개·본문·검토의견이 한 번의
  '새로 채우기'로 사라졌다. 확인 문구를 고쳐(replace-preview) 재발은 막았지만
  **돌아갈 자리**가 없었다. 사람은 확인 문구를 읽고도 누른다.

무엇을 담는가:
  파괴적 교체(`put_outline`)가 없애는 것 전부 — 목차·집필카드·본문·검토의견,
  그리고 근거·자료요청·설문 근거 지도의 목차 연결. 이것들 자체는 지워지지 않으므로
  **연결(node_uid)만** 적어 둔다.

되돌리기의 뜻(여기서 못박는다):
  - 목차·집필카드·본문은 그때 상태로 **되돌린다**(지금 것을 지우고 그때 것을 넣는다).
  - 검토의견은 **사라진 것만 되살린다**(그 뒤에 새로 생긴 의견은 건드리지 않는다).
  - 근거·자료요청은 **연결이 끊긴 것만 다시 잇는다**(사람이 그 뒤에 새로 이어 둔
    연결을 덮지 않는다). 되돌리기가 또 다른 파괴가 되면 안 된다.
"""
from __future__ import annotations

import json

from ..db import now

KEEP = 10          # 업무당 보관 개수. 오래된 것부터 지운다.


def _collect(c, pid: int) -> dict:
    nodes = [dict(r) for r in c.execute(
        "SELECT uid,parent_uid,sort,title FROM outline_nodes WHERE project_id=? ORDER BY sort", (pid,))]
    cards = [dict(r) for r in c.execute(
        "SELECT * FROM writing_cards WHERE project_id=?", (pid,))]
    drafts = [dict(r) for r in c.execute(
        "SELECT * FROM drafts WHERE project_id=?", (pid,))]
    ops = [dict(r) for r in c.execute(
        "SELECT * FROM review_opinions WHERE project_id=?", (pid,))]
    ev = {str(r["id"]): r["node_uid"] for r in c.execute(
        "SELECT id,node_uid FROM evidence WHERE project_id=? AND node_uid IS NOT NULL", (pid,))}
    rq = {str(r["id"]): r["node_uid"] for r in c.execute(
        "SELECT id,node_uid FROM data_requests WHERE project_id=? AND node_uid IS NOT NULL", (pid,))}
    sv = {str(r["id"]): r["node_uid"] for r in c.execute(
        "SELECT id,node_uid FROM survey_claims WHERE project_id=? AND node_uid IS NOT NULL", (pid,))}
    return {"nodes": nodes, "cards": cards, "drafts": drafts, "opinions": ops,
            "evidence_links": ev, "request_links": rq, "survey_links": sv}


def summarize(data: dict) -> str:
    """사람이 읽는 한 줄. 목록에서 '무엇이 든 스냅샷인지' 바로 보이게."""
    bodies = sum(1 for d in data["drafts"] if (d.get("body") or "").strip())
    parts = [f"목차 {len(data['nodes'])}", f"집필카드 {len(data['cards'])}", f"본문 {bodies}"]
    if data["opinions"]:
        parts.append(f"검토의견 {len(data['opinions'])}")
    links = len(data["evidence_links"]) + len(data["request_links"]) + len(data.get("survey_links", {}))
    if links:
        parts.append(f"목차 연결 {links}")
    return " · ".join(parts)


def take(c, pid: int, reason: str) -> int | None:
    """지금 상태를 적어 둔다. 담을 것이 하나도 없으면 찍지 않는다(빈 스냅샷은 소음)."""
    data = _collect(c, pid)
    if not data["nodes"] and not data["cards"] and not data["drafts"]:
        return None
    cur = c.execute(
        "INSERT INTO outline_snapshots(project_id,taken_at,reason,summary,data) VALUES(?,?,?,?,?)",
        (pid, now(), reason, summarize(data), json.dumps(data, ensure_ascii=False)))
    old = [r["id"] for r in c.execute(
        "SELECT id FROM outline_snapshots WHERE project_id=? ORDER BY id DESC LIMIT -1 OFFSET ?",
        (pid, KEEP))]
    for sid in old:
        c.execute("DELETE FROM outline_snapshots WHERE id=?", (sid,))
    return cur.lastrowid


def restore(c, pid: int, sid: int) -> dict:
    """스냅샷 시점으로 되돌린다. 무엇을 되살렸는지 세어 돌려준다."""
    row = c.execute("SELECT * FROM outline_snapshots WHERE id=? AND project_id=?", (sid, pid)).fetchone()
    if not row:
        return {}
    data = json.loads(row["data"])

    # ① 목차·카드·본문: 그때 것으로 바꾼다
    c.execute("DELETE FROM outline_nodes WHERE project_id=?", (pid,))
    for n in data["nodes"]:
        c.execute("INSERT INTO outline_nodes(project_id,uid,parent_uid,sort,title) VALUES(?,?,?,?,?)",
                  (pid, n["uid"], n["parent_uid"], n["sort"], n["title"]))
    c.execute("DELETE FROM writing_cards WHERE project_id=?", (pid,))
    for k in data["cards"]:
        c.execute("""INSERT INTO writing_cards(project_id,node_uid,purpose,question,message,content,length,status)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (pid, k["node_uid"], k["purpose"], k["question"], k["message"],
                   k["content"], k["length"], k["status"]))
    c.execute("DELETE FROM drafts WHERE project_id=?", (pid,))
    for d in data["drafts"]:
        c.execute("""INSERT INTO drafts(project_id,node_uid,body,ai_suggestion,strictness,model,updated_at)
                     VALUES(?,?,?,?,?,?,?)""",
                  (pid, d["node_uid"], d["body"], d["ai_suggestion"], d["strictness"],
                   d["model"], d["updated_at"]))

    # ② 검토의견: 사라진 것만 되살린다(그 뒤에 새로 생긴 의견은 그대로 둔다).
    #    id 를 그대로 넣는다 — AUTOINCREMENT 는 번호를 재사용하지 않으므로 부딪히지 않는다.
    have = {r["id"] for r in c.execute("SELECT id FROM review_opinions WHERE project_id=?", (pid,))}
    back = 0
    for o in data["opinions"]:
        if o["id"] in have:
            continue
        cols = [k for k in o.keys()]
        c.execute(f"INSERT INTO review_opinions({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                  [o[k] for k in cols])
        back += 1

    # ③ 근거·자료요청: 끊긴 연결만 다시 잇는다(사람이 그 뒤에 이어 둔 것은 덮지 않는다)
    relinked = 0
    # 설문 근거 지도(survey_links)는 v0.29 에 더했다 — 그 전에 찍은 스냅샷에는 없다.
    for table, links in (("evidence", data["evidence_links"]), ("data_requests", data["request_links"]),
                         ("survey_claims", data.get("survey_links", {}))):
        for rid, uid in links.items():
            cur = c.execute(f"SELECT node_uid FROM {table} WHERE id=? AND project_id=?", (int(rid), pid)).fetchone()
            if cur and cur["node_uid"] is None:
                c.execute(f"UPDATE {table} SET node_uid=? WHERE id=?", (uid, int(rid)))
                relinked += 1

    c.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
    return {"nodes": len(data["nodes"]), "cards": len(data["cards"]), "drafts": len(data["drafts"]),
            "opinions_restored": back, "relinked": relinked, "taken_at": row["taken_at"]}
