# -*- coding: utf-8 -*-
"""담당자 진술 — 파일 없이 근거를 세우는 짧은 경로.

긴 경로(자료 등록 → AI 분석 → 확정 → 근거표 작성)와 **결과는 같고 입구만 짧다.**
진술도 자료(resources)로 남고, 근거(evidence)로 이어지며, 최종본 부록에 나온다.
달라지는 것은 하나뿐이다 — 이것이 **문서가 아니라 사람의 말이라는 표시**가 끝까지 따라간다.

두 단계로 나눈 이유(원칙 1: AI는 제안하고 사람이 확정한다):
  ① POST /statements        진술을 자료로 저장하고, 주장 후보를 '제안'만 한다.
  ② POST /statements/{rid}/adopt  사람이 고른 것만 근거가 된다.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import connect, now
from ..services.evidence import STATEMENT_KIND
from ..services.numbering import attach_evidence_no
from ..skills.statement import split_statement

router = APIRouter(prefix="/api/projects", tags=["statements"])

# 진술로 만들어진 근거의 상태. '확인'(문서로 확인됨)과 반드시 구분되어야 한다.
STATEMENT_STATUS = "진술"


class StatementIn(BaseModel):
    text: str = ""
    name: str = ""                    # 진술 제목(비우면 날짜로 자동)
    author: str = ""                  # 누가 진술했는지(비우면 설정의 내 이름)
    provider: str | None = None


class ClaimIn(BaseModel):
    claim: str
    quote: str = ""
    opinion: bool = False


class AdoptIn(BaseModel):
    claims: list[ClaimIn] = []
    node_uid: str | None = None       # 어느 목차에 붙일지(보고전은 대개 지정한다)


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


def _author_name(c, given: str) -> str:
    if given.strip():
        return given.strip()
    r = c.execute("SELECT value FROM settings WHERE key='author_name'").fetchone()
    return (r["value"] if r else "").strip() or "담당자"


@router.post("/{pid}/statements", status_code=201)
def add_statement(pid: int, body: StatementIn):
    """진술을 자료로 저장하고, 주장 후보를 제안한다(아직 근거가 아니다)."""
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "진술 내용을 입력하세요.")
    today = date.today().isoformat()
    with connect() as c:
        _require(c, pid)
        author = _author_name(c, body.author)
        name = (body.name or "").strip() or f"{author} 진술 ({today})"
        cur = c.execute(
            "INSERT INTO resources(project_id,name,kind,source_org,base_date,trust,text,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (pid, name, STATEMENT_KIND, author, today, "진술", text, now()),
        )
        rid = cur.lastrowid

    result = split_statement(text, body.provider)

    with connect() as c:
        # 진술은 '분석'을 거치지 않는다 — 사람이 직접 쓴 것이므로 분석할 원문 해석이 없다.
        # 다만 근거로 쓰이려면 분석 행이 있어야 하므로, 요약 자리에 진술 원문을 그대로 둔다.
        # 확정(state)은 사람이 채택할 때(adopt) 비로소 붙는다.
        c.execute(
            """INSERT INTO resource_analysis(resource_id,summary,key_points,usable_for,cautions,state,model,analyzed_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(resource_id) DO UPDATE SET
                 summary=excluded.summary, key_points=excluded.key_points, state=excluded.state,
                 model=excluded.model, analyzed_at=excluded.analyzed_at""",
            (rid, text, json.dumps([x["claim"] for x in result["claims"]], ensure_ascii=False),
             "[]", json.dumps(["담당자 진술이며 문서로 확인된 자료가 아님"], ensure_ascii=False),
             "분석 완료", result["model"] or "(쪼개기: 줄 단위)", now()),
        )
        row = c.execute("SELECT * FROM resources WHERE id=?", (rid,)).fetchone()
    return {
        "resource": dict(row),
        "claims": result["claims"],
        "model": result["model"],
        "fallback": result["fallback"],   # AI 없이 줄 단위로 쪼갠 경우
        "reason": result["reason"],
    }


@router.post("/{pid}/statements/{rid}/adopt")
def adopt_statement(pid: int, rid: int, body: AdoptIn):
    """사람이 고른 주장만 근거로 만든다. 이때 진술 자료가 '사용자 확정'이 된다."""
    with connect() as c:
        _require(c, pid)
        r = c.execute("SELECT * FROM resources WHERE id=? AND project_id=? AND kind=?",
                      (rid, pid, STATEMENT_KIND)).fetchone()
        if not r:
            raise HTTPException(404, "진술 자료를 찾을 수 없습니다.")
        picked = [x for x in body.claims if x.claim.strip()]
        if not picked:
            raise HTTPException(400, "근거로 삼을 주장을 하나 이상 고르세요.")
        made = []
        for x in picked:
            cur = c.execute(
                "INSERT INTO evidence(project_id,claim,resource_id,locator,trust,status,node_uid,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (pid, x.claim.strip(), rid, (x.quote or "").strip()[:200],
                 "진술", STATEMENT_STATUS if not x.opinion else "추정",
                 body.node_uid, now()),
            )
            made.append(cur.lastrowid)
        # 사람이 골라 채택한 순간이 곧 확정이다(자료를 읽고 판단하는 절차가 곧 이 화면이었다).
        c.execute("UPDATE resource_analysis SET state='사용자 확정' WHERE resource_id=?", (rid,))
        rows = c.execute(
            "SELECT * FROM evidence WHERE id IN (%s)" % ",".join("?" * len(made)), made).fetchall()
        items = attach_evidence_no(c, pid, [dict(x) for x in rows])
    return {"created": len(items), "evidence": items}
