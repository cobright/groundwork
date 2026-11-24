# -*- coding: utf-8 -*-
"""본문 이력과 출처 표시 — 문장마다 'AI 그대로 / 사람이 고침 / 사람이 씀'을 가린다.

왜 필요한가(2026-11-24 평가, '근거 고리 닫기' ④):
  본문은 덮어쓰기라 무엇이 AI 의 글이고 무엇이 사람의 글인지 남지 않았다. 행정 문서에서
  이것은 감사 대응의 핵심이고, 원칙 1(AI는 제안, 사람이 확정)을 **사후에 증명하는** 수단이다.

어떻게:
  · AI 제안과 본문 저장을 `draft_versions` 에 차례로 남긴다(덮어쓰지 않는다).
  · 출처는 저장하지 않고 **읽을 때 계산**한다 — 지금 본문의 문장을 그 목차에 나왔던 모든 AI 제안과 견준다.
      AI 그대로  : 공백만 빼고 같은 문장이 AI 제안에 있다
      사람이 고침: 가장 닮은 AI 문장과의 닮음이 SIMILAR 이상
      사람이 씀  : 그 밖
  · 이력을 도입하기 전 업무는 AI 제안 기록이 drafts.ai_suggestion 마지막 하나뿐이다 — 그것도 함께 견준다.
    그보다 앞선 제안은 남아 있지 않으므로, 그 시절 문장은 '사람이 씀'으로 보일 수 있다(화면에 적는다).

의견만이다. 본문을 고치지 않는다(원칙 1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher

from ..db import now
from .evidence_check import split_sentences
from .quote import norm

AI, EDITED, HUMAN = "AI 그대로", "사람이 고침", "사람이 씀"
SIMILAR = 0.6
KEEP_BODIES = 30          # 본문 저장은 목차마다 최근 30개만. AI 제안은 지우지 않는다(출처의 재료다).
MERGE_MIN = 10            # 이 안에 이어진 본문 저장은 한 줄로 묶는다


def _minutes_since(ts: str) -> float:
    try:
        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 1e9
    return (datetime.now(timezone.utc) - t).total_seconds() / 60


def record(c, pid: int, uid: str, origin: str, body: str, model: str = "") -> None:
    """이력 한 줄. 바로 앞의 같은 종류와 글자가 같으면 남기지 않는다(저장 버튼을 두 번 눌러도 한 줄).

    본문은 화면이 타자를 멈출 때마다(0.5초) 저장한다 — 그대로 다 남기면 이력이 글자 단위로 쌓여
    정작 '언제 무엇으로 바뀌었나'가 묻힌다. 그래서 바로 앞 줄이 본문이고 MERGE_MIN 분 안이면 그 줄을 고쳐 쓴다.
    AI 제안이 사이에 끼면 새 줄로 시작한다(제안을 반영한 순간이 남아야 한다)."""
    last = c.execute("SELECT id, origin, body, created_at FROM draft_versions WHERE project_id=? AND node_uid=? "
                     "ORDER BY id DESC LIMIT 1", (pid, uid)).fetchone()
    if last and last["origin"] == origin and last["body"] == body:
        return
    if origin == "본문" and last and last["origin"] == "본문" and _minutes_since(last["created_at"]) < MERGE_MIN:
        c.execute("UPDATE draft_versions SET body=? WHERE id=?", (body, last["id"]))
        return
    c.execute("INSERT INTO draft_versions(project_id,node_uid,origin,body,model,created_at) VALUES(?,?,?,?,?,?)",
              (pid, uid, origin, body, model, now()))
    if origin == "본문":
        c.execute("DELETE FROM draft_versions WHERE project_id=? AND node_uid=? AND origin='본문' AND id NOT IN "
                  "(SELECT id FROM draft_versions WHERE project_id=? AND node_uid=? AND origin='본문' "
                  "ORDER BY id DESC LIMIT ?)", (pid, uid, pid, uid, KEEP_BODIES))


def ai_texts(c, pid: int, uid: str) -> list[str]:
    out = [r["body"] for r in c.execute(
        "SELECT body FROM draft_versions WHERE project_id=? AND node_uid=? AND origin='AI 제안'", (pid, uid))]
    d = c.execute("SELECT ai_suggestion FROM drafts WHERE project_id=? AND node_uid=?", (pid, uid)).fetchone()
    if d and d["ai_suggestion"] and d["ai_suggestion"] not in out:
        out.append(d["ai_suggestion"])
    return out


def classify(body: str, ai: list[str]) -> dict:
    """지금 본문의 문장별 출처와 개수."""
    ai_sents = [norm(s) for t in ai for s in split_sentences(t)]
    ai_set = set(ai_sents)
    rows = []
    for s in split_sentences(body):
        n = norm(s)
        if not n:
            continue
        if n in ai_set:
            kind = AI
        else:
            best = max((SequenceMatcher(None, n, a).ratio() for a in ai_sents), default=0.0)
            kind = EDITED if best >= SIMILAR else HUMAN
        rows.append({"sentence": s[:200], "origin": kind})
    counts = {k: sum(1 for r in rows if r["origin"] == k) for k in (AI, EDITED, HUMAN)}
    return {"sentences": rows, "counts": counts, "ai_versions": len(ai)}


def for_node(c, pid: int, uid: str, body: str) -> dict:
    return classify(body, ai_texts(c, pid, uid))


def history(c, pid: int, uid: str) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT id, origin, body, model, created_at FROM draft_versions WHERE project_id=? AND node_uid=? "
        "ORDER BY id DESC", (pid, uid))]
