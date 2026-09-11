# -*- coding: utf-8 -*-
"""목차에 연결된 근거를 '쓸 수 있는 형태'로 모은다 — 초고와 검토가 함께 쓰는 한 곳.

예전엔 outline.py 와 review.py 에 같은 함수가 복제돼 있었다. 근거에 새 성격
(담당자 진술)이 생기면서 한쪽만 고치면 초고와 검토가 서로 다른 근거를 보게 되므로 합쳤다.

`resource_kind` 를 함께 실어 보내는 이유:
  담당자 진술은 **문서 근거가 아니다.** 사람이 아는 바를 적은 것이므로 검증된 자료와
  같은 무게로 취급되면 안 된다. 그 구분이 프롬프트까지 그대로 전달되어야 한다.
"""
from __future__ import annotations

from .numbering import evidence_numbers

# 담당자가 직접 진술한 사실. 파일 근거가 아니라는 표시.
STATEMENT_KIND = "담당자 진술"


def linked_evidence(c, pid: int, uid: str) -> list[dict]:
    """이 목차(uid)에 연결된 근거 + 근거자료의 요약·확정상태·종류를 함께 모은다."""
    rows = c.execute(
        "SELECT * FROM evidence WHERE project_id=? AND node_uid=? ORDER BY id", (pid, uid)).fetchall()
    nos = evidence_numbers(c, pid)   # 번호는 업무 전체 기준 — 화면·부록과 같은 번호를 쓴다
    out = []
    for e in rows:
        d = dict(e)
        d["ev_no"] = nos.get(d["id"], "")
        if d.get("resource_id"):
            r = c.execute("SELECT name,kind FROM resources WHERE id=?", (d["resource_id"],)).fetchone()
            a = c.execute("SELECT summary,state FROM resource_analysis WHERE resource_id=?",
                          (d["resource_id"],)).fetchone()
            d["resource_name"] = r["name"] if r else ""
            d["resource_kind"] = r["kind"] if r else ""
            d["resource_summary"] = a["summary"] if a else ""
            d["state"] = a["state"] if a else "분석 전"
        else:
            d["resource_name"] = ""; d["resource_kind"] = ""
            d["resource_summary"] = ""; d["state"] = ""
        out.append(d)
    return out


def evidence_mark(e: dict) -> str:
    """근거 한 건을 프롬프트에서 뭐라고 부를지. 진술을 확정 자료로 위장하지 않는다."""
    if e.get("resource_kind") == STATEMENT_KIND:
        return "진술"
    state = e.get("state", "")
    if not state:
        return "근거자료 없음"
    return "확정" if state == "사용자 확정" else "미확정"
