# -*- coding: utf-8 -*-
"""배점 대비 충실도 지도 — 심사 배점 · 분량 · 확정 근거를 한 표에 놓는다. 규칙만, AI 를 부르지 않는다.

왜 필요한가(2026-11-24 평가, 2단계 '문서 전체를 보는 눈'):
  배점은 가이드라인 분석이 집필카드에 문장으로 실어 두었지만(guideline.score_note), 그 무게만큼
  쓰였는지는 아무도 보지 않았다. '30점짜리 항목에 근거 0건'·'5점 항목에 분량이 몰림' 이 보여야 한다.

무엇을 세는가:
  · 배점: 집필카드의 [심사배점] 문장을 되읽는다(guideline.parse_score_note — 문장을 만드는 곳과 한 파일).
  · 분량: 확정 본문의 글자 수(공백 제외). 배점이 걸린 목차 + 그 아래 목차 중 자기 배점이 없는 것까지.
  · 근거: 그 목차들에 연결된 근거 중 '확정'·'진술'(초고에 넘어가는 것 — evidence_mark 와 같은 기준).
  같은 심사항목에 목차 여럿이 걸리면 한 줄로 모은다(guideline.match_scores 가 그렇게 짝짓는다).

짚는 것(의견만, 막지 않는다 — 배점과 분량의 관계는 사람이 판단한다):
  · 확정 근거 0건인 배점 항목   · 본문이 없는 배점 항목
  · 분량 몫이 배점 몫의 절반도 안 되는 항목(배점 몫 10% 이상일 때만 — 작은 항목은 흔들림이 크다)
"""
from __future__ import annotations

from .evidence import evidence_mark, linked_evidence
from .guideline import parse_score_note
from .numbering import sections_with_body

THIN = 0.5          # 분량 몫 / 배점 몫 이 이보다 작으면 '얇다'
MIN_SHARE = 0.10    # 배점 몫이 이보다 작은 항목은 얇다고 짚지 않는다


def _chars(body: str) -> int:
    return len("".join((body or "").split()))


def build(c, pid: int) -> dict:
    secs = sections_with_body(c, pid)
    cards = {r["node_uid"]: r["purpose"] for r in c.execute(
        "SELECT node_uid, purpose FROM writing_cards WHERE project_id=?", (pid,))}
    scored = {s["uid"]: parse_score_note(cards.get(s["uid"], "")) for s in secs}
    by_uid = {s["uid"]: s for s in secs}

    # 배점이 걸린 목차마다 '그 아래에서 자기 배점이 없는 목차'까지 한 묶음으로
    def group(uid: str) -> list[dict]:
        out, stack = [], [uid]
        while stack:
            u = stack.pop()
            out.append(by_uid[u])
            stack += [s["uid"] for s in secs if s["parent_uid"] == u and not scored.get(s["uid"])]
        return out

    covered: set[str] = set()
    rows: dict[str, dict] = {}
    for s in secs:
        hits = scored.get(s["uid"])
        if not hits:
            continue
        members = group(s["uid"])
        covered |= {m["uid"] for m in members}
        for h in hits:
            r = rows.setdefault(h["label"], {"label": h["label"], "points": h["points"], "low": False,
                                             "nodes": [], "_uids": []})
            if r["points"] is None and h["points"] is not None:
                r["points"] = h["points"]
            r["low"] = r["low"] or h["low"]
            r["nodes"].append(f"{s['number']} {s['title']}")
            r["_uids"] += [m["uid"] for m in members if m["uid"] not in r["_uids"]]

    for r in rows.values():
        uids = r.pop("_uids")
        r["chars"] = sum(_chars(by_uid[u]["body"]) for u in uids)
        ev = [e for u in uids for e in linked_evidence(c, pid, u)]
        r["evidence"] = sum(1 for e in ev if evidence_mark(e) in ("확정", "진술"))
        r["evidence_linked"] = len(ev)

    items = list(rows.values())
    total_pts = sum(r["points"] or 0 for r in items)
    total_chars = sum(r["chars"] for r in items)
    for r in items:
        r["point_share"] = round((r["points"] or 0) / total_pts, 3) if total_pts else None
        r["char_share"] = round(r["chars"] / total_chars, 3) if total_chars else None
        flags = []
        if r["chars"] == 0:
            flags.append("본문 없음")
        if r["evidence"] == 0:
            flags.append("확정 근거 0건")
        if (r["point_share"] or 0) >= MIN_SHARE and total_chars and r["chars"] \
                and r["char_share"] < r["point_share"] * THIN:
            flags.append(f"분량 몫 {r['char_share']:.0%} < 배점 몫 {r['point_share']:.0%}의 절반")
        r["flags"] = flags
    items.sort(key=lambda r: -(r["points"] or 0))

    unscored = [{"node": f"{s['number']} {s['title']}", "chars": _chars(s["body"])}
                for s in secs if s["uid"] not in covered and s["depth"] == 1]
    return {"items": items, "unscored": unscored, "total_points": total_pts, "total_chars": total_chars}
