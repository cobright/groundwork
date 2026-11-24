# -*- coding: utf-8 -*-
"""원문 인용 구간 — '이 글이 자료 본문에 글자 그대로 있는가'를 가리는 유일한 자리.

왜 필요한가(2026-11-24 평가, '근거 고리 닫기'):
  근거가 '사람이 쓴 주장 한 줄 + 자료 통째'라서 초고는 AI 요약을 보고 썼고, 점검기는 숫자만 대조했다.
  근거에 **원문 구간**을 붙이면 기관명·날짜·조건 같은 숫자 아닌 사실도 기계가 확인할 수 있다.

무엇을 같다고 보는가 — 일부러 좁게:
  · 띄어쓰기·줄바꿈 차이는 무시한다(파일을 읽으며 줄이 갈리고, AI 가 옮기며 공백을 바꾼다).
  · 표 칸 구분자(│ |)도 공백으로 본다 — doc_read 가 표를 ' │ ' 로 펴기 때문에, 한 줄을 옮기면 섞인다.
  · 그 밖의 것(맞춤법·조사·숫자 표기)은 다르면 다르다. 비슷하면 통과시키는 순간 '인용'이 아니다.
"""
from __future__ import annotations

import re

_SPACE = re.compile(r"[\s│|]+")
MIN_LEN = 4          # 이보다 짧은 인용은 어디에나 있어 확인하는 의미가 없다


def norm(s: str) -> str:
    return _SPACE.sub("", s or "")


def quote_in(quote: str, source: str) -> bool:
    """인용 구간이 원문에 (공백·표 구분자만 빼고) 그대로 있는가. 빈 인용은 False."""
    q = norm(quote)
    return bool(q) and q in norm(source)


def quote_state(quote: str, source: str) -> str:
    """'없음'(인용을 달지 않음) · '일치' · '불일치'(원문에서 그대로 찾지 못함)."""
    if not (quote or "").strip():
        return "없음"
    return "일치" if quote_in(quote, source) else "불일치"
