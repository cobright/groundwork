# -*- coding: utf-8 -*-
"""가이드라인 두 건의 분석 결과를 견준다 — 정정 공고에서 무엇이 달라졌는가.

공모에서 정정 공고는 흔하다. 그런데 바뀌는 것은 대개 **문서 전체가 아니라 몇 줄**이다
(마감일 하루, 배점 5점, 서식 한 장). 44쪽을 다시 읽어 눈으로 찾는 것은 사람이 할 일이 아니다.

무엇을 견주는가(담당자가 놓치면 실제로 손해 보는 것부터):
  ① 접수 마감일  — 하루 늦게 알면 제출을 못 한다
  ② 심사 배점    — 분량 배분이 통째로 달라진다
  ③ 목차(제출서식) — 항목이 늘거나 빠지면 다시 써야 한다
  ④ 필요한 자료  — 부서 요청을 다시 돌려야 한다

**다시 읽지 않는다.** 두 분석 결과(guidelines.analysis)를 그대로 견준다 —
분석은 이미 사람이 범위를 골라 확인한 것이므로, 여기서 다시 추측을 보태지 않는다.
"""
from __future__ import annotations


def _paths(tree: list[dict], prefix: str = "") -> list[str]:
    """목차를 '상위 > 하위' 경로 문자열로 편다(순서가 바뀐 것과 내용이 바뀐 것을 가르려고)."""
    out = []
    for n in tree or []:
        p = f"{prefix} > {n['title']}" if prefix else n["title"]
        out.append(p)
        out += _paths(n.get("children") or [], p)
    return out


def _score_map(analysis: dict) -> dict[str, str]:
    """심사항목 이름 → 배점 글자. 같은 이름이 여럿이면 뒤엣것이 이긴다(표에서 아래가 구체적)."""
    out = {}
    for s in analysis.get("scoring") or []:
        key = (s.get("label") or s.get("item") or "").strip()
        if key:
            out[key] = (s.get("points_text") or "").strip()
    return out


def _due(analysis: dict) -> str:
    cands = ((analysis.get("basic") or {}).get("마감일후보")) or []
    return cands[-1] if cands else ""


def _needs(analysis: dict) -> set[str]:
    return {(n.get("need") or "").strip() for n in (analysis.get("needs") or []) if (n.get("need") or "").strip()}


def compare(old: dict, new: dict) -> dict:
    """old(이전 분석) → new(이번 분석) 로 무엇이 달라졌는지. 바뀐 것만 담는다."""
    changes: list[dict] = []

    # ① 마감일
    od, nd = _due(old), _due(new)
    if od != nd:
        changes.append({"kind": "마감일", "rank": 0,
                        "before": od or "(못 찾음)", "after": nd or "(못 찾음)",
                        "what": "접수 마감일이 달라졌습니다. 업무의 마감일도 함께 고치세요."})

    # ② 배점
    om, nm = _score_map(old), _score_map(new)
    for k in sorted(set(nm) - set(om)):
        changes.append({"kind": "배점 추가", "rank": 1, "before": "", "after": f"{k} {nm[k]}".strip(),
                        "what": "새로 생긴 심사항목입니다. 대응하는 목차가 있는지 보세요."})
    for k in sorted(set(om) - set(nm)):
        changes.append({"kind": "배점 삭제", "rank": 1, "before": f"{k} {om[k]}".strip(), "after": "",
                        "what": "없어진 심사항목입니다. 그 항목에 쏟던 분량을 줄여도 됩니다."})
    for k in sorted(set(om) & set(nm)):
        if om[k] != nm[k]:
            changes.append({"kind": "배점 변경", "rank": 1, "before": f"{k} {om[k]}".strip(),
                            "after": f"{k} {nm[k]}".strip(),
                            "what": "배점이 달라졌습니다. 분량 배분을 다시 보세요."})

    # ③ 목차(제출서식)
    op, np_ = set(_paths(old.get("tree") or [])), set(_paths(new.get("tree") or []))
    for p in sorted(np_ - op):
        changes.append({"kind": "목차 추가", "rank": 2, "before": "", "after": p,
                        "what": "새로 생긴 항목입니다. 목차에 넣고 써야 합니다."})
    for p in sorted(op - np_):
        changes.append({"kind": "목차 삭제", "rank": 2, "before": p, "after": "",
                        "what": "없어진 항목입니다. 이미 썼다면 그대로 두어도 감점은 아니지만 분량만 늡니다."})

    # ④ 필요한 자료
    on, nn = _needs(old), _needs(new)
    for n in sorted(nn - on):
        changes.append({"kind": "자료 추가", "rank": 3, "before": "", "after": n,
                        "what": "새로 요구된 자료입니다. 부서에 요청하세요."})
    for n in sorted(on - nn):
        changes.append({"kind": "자료 삭제", "rank": 3, "before": n, "after": "",
                        "what": "더 이상 요구되지 않는 자료입니다."})

    changes.sort(key=lambda c: (c["rank"], c["kind"]))
    return {
        "changed": len(changes),
        "changes": changes,
        "summary": {
            "due": {"before": od, "after": nd},
            "scoring": {"before": len(om), "after": len(nm)},
            "outline": {"before": len(op), "after": len(np_)},
            "needs": {"before": len(on), "after": len(nn)},
        },
    }
