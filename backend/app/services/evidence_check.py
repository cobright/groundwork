# -*- coding: utf-8 -*-
"""근거 점검기 — 본문의 숫자와 근거 번호를 근거 **원문**과 규칙으로 대조한다. AI 를 부르지 않는다.

왜 필요한가(2026-11-24 기능 분석):
  '확정한 근거로만 쓴다'(원칙 2)를 지키는 장치가 초고 지시문("근거에 있는 사실만 쓰라")뿐이었다.
  그것을 잡는 사실확인 검토도 또 다른 AI 였다. 숫자가 틀린 계획서가 '근거 부록'을 달고 나가면
  부록이 오히려 틀린 내용에 신뢰를 실어 준다. 그래서 기계적으로 확인할 수 있는 것은 기계가 확인한다.

무엇을 보는가 (문장 단위):
  · 없는 근거 번호       — (근거: E-009) 인데 이 업무에 E-009 가 없다                       [중대]
  · 원문에 없는 숫자     — 인용한 근거의 원문·주장 어디에도 그 숫자가 그대로는 없다       [중요]
  · 미확정 근거 인용     — 사람이 확정하지 않은 자료를 근거로 달았다                         [중요]
  · 원본이 바뀐 근거     — 인용한 근거에 '근거 자료 변경됨' 신호가 켜져 있다               [중요]
  · 근거 없는 수치 문장  — 양을 말하는 숫자(명·%·원·개소…)가 있는데 근거 번호가 없다      [중요]
  ([추정]·[확인 필요] 로 스스로 표시한 문장은 '근거 없는 수치'로 짚지 않는다 — 이미 정직하게 표시했다.)

대조하는 '원문'은 **자료 원문(resources.text) + 근거 항목의 주장·위치**다. AI 가 만든 자료 요약은 넣지 않는다 —
요약이 틀렸을 때 그 틀린 숫자를 '근거에 있다'고 통과시키게 되기 때문이다.

한계(의견에 그대로 적는다): 숫자를 글자 그대로 찾는다. 단위를 바꿔 쓴 값(3,000만원 ↔ 3천만원)이나
계산한 값(증가율·합계)은 '원문에 없음'으로 나온다. 그래서 고치라는 뜻이 아니라 **확인하라**는 뜻이다.
의견만 낸다. 본문을 고치지 않는다(원칙 1).
"""
from __future__ import annotations

import re

from .evidence import evidence_mark
from .numbering import evidence_numbers

# (근거: E-001) · (근거: E-001, E-003) · (근거 : E-1)
_CITE = re.compile(r"\(\s*근거\s*[:：]\s*([^)]*)\)")
_EVNO = re.compile(r"E-\d+")
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
# 양을 말하는 숫자의 단위. 이게 붙어야 '근거 없는 수치'로 짚는다(연도·순번·조항 번호를 짚지 않으려고).
_QTY_UNIT = re.compile(
    r"^\s*(?:%p|%|퍼센트|명|인|가구|세대|개소|개|곳|건|회|차례|원|천원|만원|억원|조원|만|억|천|조|배|"
    r"㎡|m²|㎢|km|ha|톤|t|kg|대|채|동|호|석|권|시간|분|일간|개월|년간|주간|세)")
_MARKED = ("[추정", "[확인 필요")
_LEVEL_ORDER = {"중대": 0, "중요": 1, "참고": 2}


def norm_num(tok: str) -> str:
    """'15,600' → '15600', '45.90' → '45.9', '26.0' → '26'."""
    s = tok.replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def numbers_in(text: str) -> list[tuple[str, str, bool]]:
    """(원래 글자, 정규화 값, 양을 말하는가) 목록. 근거 번호(E-001) 안의 숫자는 뺀다."""
    text = _EVNO.sub(" ", text or "")
    out = []
    for m in _NUM.finditer(text):
        tok = m.group(0).rstrip(",")
        out.append((tok, norm_num(tok), bool(_QTY_UNIT.match(text[m.end():]))))
    return out


def split_sentences(text: str) -> list[str]:
    """줄과 문장 끝(. ! ?)으로 나눈다. 문장 뒤에 따로 떨어진 '(근거: …)' 는 앞 문장에 붙인다."""
    parts: list[str] = []
    for line in (text or "").splitlines():
        for seg in re.split(r"(?<=[.!?。])\s+", line.strip()):
            seg = seg.strip()
            if not seg:
                continue
            if parts and _CITE.sub("", seg).strip(" .") == "" and _CITE.search(seg):
                parts[-1] += " " + seg          # "…늘었다. (근거: E-001)" 의 꼬리
            else:
                parts.append(seg)
    return parts


def evidence_index(c, pid: int) -> dict[str, dict]:
    """근거 번호(E-001) → {mark, source_changed, source(대조할 원문), claim}. 업무 전체."""
    nos = evidence_numbers(c, pid)
    out: dict[str, dict] = {}
    for e in c.execute("SELECT * FROM evidence WHERE project_id=?", (pid,)).fetchall():
        d = dict(e)
        no = nos.get(d["id"])
        if not no:
            continue
        src = [d.get("claim") or "", d.get("locator") or ""]
        d["resource_kind"], d["state"] = "", ""
        if d.get("resource_id"):
            r = c.execute("SELECT kind,text FROM resources WHERE id=?", (d["resource_id"],)).fetchone()
            a = c.execute("SELECT state FROM resource_analysis WHERE resource_id=?", (d["resource_id"],)).fetchone()
            if r:
                d["resource_kind"] = r["kind"]
                src.append(r["text"] or "")
            d["state"] = a["state"] if a else "분석 전"
        out[no] = {"mark": evidence_mark(d), "source_changed": bool(d.get("source_changed")),
                   "nums": {n for _, n, _ in numbers_in("\n".join(src))}, "claim": d.get("claim") or ""}
    return out


def _f(level, kind, sentence, text, **kw):
    return {"level": level, "kind": kind, "sentence": sentence[:160], "text": text, **kw}


def check_text(text: str, index: dict[str, dict]) -> list[dict]:
    """본문 한 덩어리를 점검해 의견 목록을 돌려준다(심각한 것부터)."""
    found: list[dict] = []
    for sent in split_sentences(text):
        cited: list[str] = []
        for m in _CITE.finditer(sent):
            cited += _EVNO.findall(m.group(1))
        body = _CITE.sub(" ", sent)
        nums = numbers_in(body)
        marked = any(k in sent for k in _MARKED)

        known = []
        for no in dict.fromkeys(cited):             # 순서 유지 + 중복 제거
            ev = index.get(no)
            if ev is None:
                found.append(_f("중대", "없는 근거 번호", sent,
                                f"{no} 는 이 업무의 근거표에 없습니다. 번호가 틀렸거나 지워진 근거입니다.", ev=no))
                continue
            known.append((no, ev))
            if ev["mark"] in ("미확정", "근거자료 없음"):
                found.append(_f("중요", "미확정 근거 인용", sent,
                                f"{no} 는 아직 확정하지 않은 자료입니다({ev['mark']}). 확정 전엔 근거가 아닙니다.", ev=no))
            if ev["source_changed"]:
                found.append(_f("중요", "원본이 바뀐 근거 인용", sent,
                                f"{no} 의 자료가 수정됐습니다. 이 문장이 아직 맞는지 원문을 다시 보세요.", ev=no))

        if known:
            pool = set().union(*(ev["nums"] for _, ev in known))
            missing = list(dict.fromkeys(tok for tok, n, _ in nums if n not in pool))
            if missing:                              # 한 문장에 의견 하나 — 숫자마다 따로 내면 시끄럽다
                nos = ", ".join(no for no, _ in known)
                found.append(_f("중요", "원문에 없는 숫자", sent,
                                f"{', '.join('‘' + t + '’' for t in missing[:5])} 를 {nos} 의 원문에서 그대로 "
                                "찾지 못했습니다. 단위를 바꿔 썼거나 계산한 값이면 맞는지 확인만 하세요.",
                                number=missing[0], ev=nos))
        elif not cited and not marked:
            qty = [tok for tok, _, is_qty in nums if is_qty]
            if qty:
                found.append(_f("중요", "근거 없는 수치 문장", sent,
                                f"수치({', '.join(qty[:4])})가 있는데 근거 번호가 없습니다. "
                                "근거를 달거나, 근거가 없으면 [확인 필요]로 표시하세요.", number=qty[0]))
    found.sort(key=lambda f: _LEVEL_ORDER[f["level"]])
    return found


def check_project(c, pid: int) -> list[dict]:
    """업무 전체의 확정 본문을 목차 순서대로 점검한다. 각 의견에 목차 번호·제목을 붙인다."""
    from .numbering import sections_with_body
    index = evidence_index(c, pid)
    out = []
    for s in sections_with_body(c, pid):
        for f in check_text(s["body"], index):
            out.append({**f, "section": f"{s['number']} {s['title']}", "uid": s["uid"]})
    return out
