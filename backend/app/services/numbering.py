# -*- coding: utf-8 -*-
"""근거 번호(E-번호)를 만드는 유일한 자리.

원칙: 근거는 업무 안에서 하나의 정체성을 가진다.
등록 순서(id 오름차순)로 업무 전체에 걸쳐 한 번만 번호를 매기고,
근거표·초고·검토·최종본 부록이 모두 이 번호를 그대로 쓴다.
그래야 AI가 본문에 단 '(근거: E-003)' 이 부록 근거표의 E-003 과 같은 항목을 가리킨다.
"""
from __future__ import annotations


def evidence_numbers(c, pid: int) -> dict[int, str]:
    """{근거 id: 'E-003'} 를 돌려준다."""
    rows = c.execute("SELECT id FROM evidence WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    return {r["id"]: "E-%03d" % i for i, r in enumerate(rows, 1)}


def attach_evidence_no(c, pid: int, items: list[dict]) -> list[dict]:
    """근거 dict 목록에 ev_no 를 붙인다(원본 목록을 그대로 반환)."""
    nos = evidence_numbers(c, pid)
    for d in items:
        d["ev_no"] = nos.get(d.get("id"), "")
    return items


# ────────────── 목차 번호 ──────────────
# 번호는 저장하지 않고 항상 여기서 계산한다(목차를 재정렬하면 번호도 따라 바뀐다).
# 예전에는 이 walk 가 outline/review/requests/export_docx 에 네 벌 흩어져 있었다.

def outline_rows(c, pid: int) -> list[dict]:
    """목차를 화면에 보이는 순서대로 편 목록.
    각 항목: uid, parent_uid, sort, title, number('2.1'), depth(1부터).
    부모가 사라진 항목은 조용히 없어지지 않도록 최상위로 끌어올린다."""
    nodes = c.execute(
        "SELECT uid,parent_uid,sort,title FROM outline_nodes WHERE project_id=? ORDER BY sort", (pid,)
    ).fetchall()
    known = {n["uid"] for n in nodes}
    children: dict = {}
    for n in nodes:
        parent = n["parent_uid"] if n["parent_uid"] in known else None
        children.setdefault(parent, []).append(n)
    for a in children.values():
        a.sort(key=lambda x: x["sort"])

    out: list[dict] = []
    seen = set()

    def walk(parent, depth, prefix):
        for i, n in enumerate(children.get(parent, [])):
            if n["uid"] in seen:      # 순환 참조 방어
                continue
            seen.add(n["uid"])
            num = f"{prefix}{i + 1}"
            out.append({"uid": n["uid"], "parent_uid": n["parent_uid"], "sort": n["sort"],
                        "title": n["title"], "number": num, "depth": depth})
            walk(n["uid"], depth + 1, num + ".")

    walk(None, 1, "")
    return out


def number_map(c, pid: int) -> tuple[dict, dict]:
    """({uid: '2.1'}, {uid: '제목'}) — 표·목록에서 목차를 가리킬 때."""
    rows = outline_rows(c, pid)
    return {r["uid"]: r["number"] for r in rows}, {r["uid"]: r["title"] for r in rows}


def title_and_number(c, pid: int, uid: str) -> tuple[str, str]:
    """목차 항목 하나의 (제목, 번호). 없는 항목이면 ('', '')."""
    for r in outline_rows(c, pid):
        if r["uid"] == uid:
            return r["title"], r["number"]
    return "", ""


def sections_with_body(c, pid: int) -> list[dict]:
    """목차 순서대로 확정 본문까지 붙인 목록(문서 전체 검토·미리보기·최종본 공용)."""
    out = []
    for r in outline_rows(c, pid):
        d = c.execute("SELECT body FROM drafts WHERE project_id=? AND node_uid=?", (pid, r["uid"])).fetchone()
        out.append({**r, "body": d["body"] if d else ""})
    return out
