# -*- coding: utf-8 -*-
"""항목 간 정합성 점검(규칙) — 같은 지표가 목차마다 다른 값으로 나오는 곳을 짚는다. AI 를 부르지 않는다.

왜 필요한가(2026-11-24 평가, 2단계 '문서 전체를 보는 눈'):
  초고·점검·검토가 모두 목차 하나씩이다. 1장에 '65세 이상 인구 15,600명', 3장에 '15,700명'으로 써도
  아무도 잡지 않았다. 공모 심사에서 실제로 감점되는 것은 이런 문서 전체의 어긋남이다.

어떻게 '같은 지표'를 알아보는가 — 일부러 좁게:
  문장을 쉼표·'및'·'이며'·'이고' 로 나눈 마디마다, 양을 말하는 숫자(명·%·원·개소… — evidence_check 와 같은 단위)
  앞의 말을 **주어**로 본다. 열쇠 = 주어의 마지막 두 낱말(조사를 떼고) + 연도 + 단위.
    "2026년 가온읍의 총인구는 18,420명"     → (가온읍 총인구, 2026, 명)
    "총인구는 2024년 43,610명, 2025년 42,780명" → 두 번째 마디는 주어가 비어 앞 마디의 주어를 잇는다
  연도가 여럿인 문장에서 연도를 못 박을 수 없는 숫자("각각 14,840명, 15,220명")는 건너뛴다 — 틀리게 잇느니 안 본다.
  열쇠가 같은데 값이 다르면 의견 하나. 지명이 다르면 열쇠가 달라 섞이지 않는다(가온읍 총인구 ≠ 북계면 총인구).

한계(의견에 그대로 적는다): 낱말이 조금만 달라도(총인구/전체 인구) 같은 지표로 못 본다 — 놓치는 쪽으로 좁혔다.
단위를 바꿔 쓴 값(3억 원 ↔ 30,000만 원)은 다른 값으로 나온다. 그래서 고치라는 뜻이 아니라 **확인하라**는 뜻이다.
의견만 낸다. 본문을 고치지 않는다(원칙 1).
"""
from __future__ import annotations

import re

from .evidence_check import _CITE, _QTY_UNIT, norm_num, split_sentences

# 숫자 + 단위. 단위는 evidence_check 의 _QTY_UNIT 과 같은 목록을 쓴다(따로 두면 둘이 어긋난다).
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_YEAR = re.compile(r"((?:19|20)\d{2})\s*년")
_CLAUSE = re.compile(r",|，|、|\s및\s|이며|이고|이었고|였고|그리고")
_PARTICLE = re.compile(r"(은|는|이|가|의|을|를|도|만|에서|에는|에|으로|로|와|과|보다)$")
# 주어로 치지 않는 말(양을 꾸밀 뿐 지표 이름이 아니다)
_FILLER = {"약", "총", "각각", "모두", "기준", "같은", "기간", "현재", "올해", "연간", "평균", "전체", "모두", "합계"}



_RANGE = {"이상", "이하", "미만", "초과"}


def _subject(seg: str) -> str:
    """마디 앞의 말에서 지표 이름(마지막 세 낱말)을 뽑는다. 없으면 빈 글자.

    '65세 이상' 은 한 덩어리로 붙인다 — 떼면 65세 이상 인구와 75세 이상 인구가 같은 지표가 된다.
    세 낱말까지 두는 이유: 지명이 빠지면 '가온읍 고령인구'와 군 전체 고령인구가 섞인다(가장 흔한 헛경보)."""
    seg = _YEAR.sub(" ", seg)
    seg = re.sub(r"[()\[\]“”\"'‘’·:~\-]", " ", seg)
    words: list[str] = []
    for w in seg.split():
        w = _PARTICLE.sub("", w.strip(",."))
        if not w or w in _FILLER or not re.search(r"[가-힣]", w):
            continue
        if re.fullmatch(r"[\d,.]+", w):
            continue
        if w in _RANGE and words:
            words[-1] += w
            continue
        if not re.search(r"[가-힣]{2,}|\d+[가-힣]", w):
            continue
        words.append(w)
    return " ".join(words[-3:])


def facts_in(sentence: str) -> list[dict]:
    """문장 하나의 (지표, 연도, 단위, 값) 목록."""
    body = _CITE.sub(" ", sentence)
    years_in_sentence = set(_YEAR.findall(body))
    out, subject, year, prefix = [], "", "", []
    start = 0
    for m in _NUM.finditer(body):
        tail = body[m.end():]
        u = _QTY_UNIT.match(tail)
        if not u:
            continue
        if _YEAR.match(body[m.start():]):          # '2026년' 자체는 값이 아니다
            continue
        if u.group(0).strip() == "세":              # '65세'는 값이 아니라 지표 이름의 일부(65세 이상 인구)다
            continue
        seg = body[start:m.start()]
        cut = list(_CLAUSE.finditer(seg))
        clause = seg[cut[-1].end():] if cut else seg
        new_subject = _subject(clause)
        ys = _YEAR.findall(clause)
        if "각각" in body and not ys:
            # "…은 같은 기간 각각 14,840명, 15,220명" — 어느 값이 어느 해인지 문장이 말하지 않는다
            if new_subject:
                subject = new_subject
            start = m.end() + u.end()
            continue
        if new_subject:
            # 같은 문장 앞 마디의 꾸밈말(대개 지명)을 잇는다 — "가온읍의 총인구는 …, 65세 이상 인구는 …" 의
            # 뒤 마디를 군 전체의 65세 이상 인구와 섞지 않으려고.
            if subject and not prefix:
                prefix = subject.split()[:-1]
            if prefix and not set(prefix) & set(new_subject.split()):
                new_subject = " ".join((prefix + new_subject.split())[-3:])
            subject = new_subject
            year = ys[-1] if ys else (next(iter(years_in_sentence)) if len(years_in_sentence) == 1 else "")
            ambiguous = (not ys and len(years_in_sentence) > 1) or len(set(ys)) > 1   # "2024년과 2026년 …은 35%"
        else:
            # 주어 없는 마디("…, 2025년 42,780명")는 앞 마디의 주어를 잇는다. 연도가 없으면 못 박을 수 없다.
            year = ys[-1] if ys else ""
            ambiguous = not ys or len(set(ys)) > 1
        if not subject:
            # 앞에 주어가 아직 없는 숫자('65세 이상 인구는…' 의 65세)는 다음 숫자의 주어 일부다 — 자리를 넘기지 않는다
            continue
        start = m.end() + u.end()
        if ambiguous:
            continue
        out.append({"subject": subject, "year": year, "unit": u.group(0).strip(),
                    "value": norm_num(m.group(0).rstrip(",")), "text": m.group(0).rstrip(",") + u.group(0).strip()})
    return out


def check_sections(sections: list[dict]) -> list[dict]:
    """목차별 본문 목록(number, title, body)을 받아 같은 지표가 다른 값으로 나오는 곳을 돌려준다."""
    seen: dict[tuple, dict[str, list]] = {}
    for s in sections:
        where = f"{s.get('number', '')} {s.get('title', '')}".strip()
        for sent in split_sentences(s.get("body") or ""):
            for f in facts_in(sent):
                key = (f["subject"], f["year"], f["unit"])
                seen.setdefault(key, {}).setdefault(f["value"], []).append(
                    {"where": where, "text": f["text"], "sentence": sent[:120]})
    found = []
    for (subject, year, unit), values in seen.items():
        if len(values) < 2:
            continue
        name = f"{subject}" + (f"({year}년)" if year else "")
        spots = [f"{v[0]['text']} — {v[0]['where']}" + (f" 외 {len(v) - 1}곳" if len(v) > 1 else "")
                 for v in values.values()]
        found.append({"indicator": name, "unit": unit, "values": list(values.keys()),
                      "text": f"‘{name}’ 이(가) 다른 값으로 나옵니다: " + " / ".join(spots),
                      "spots": [x for v in values.values() for x in v]})
    return found


def check_project(c, pid: int) -> list[dict]:
    from .numbering import sections_with_body
    return check_sections(sections_with_body(c, pid))
