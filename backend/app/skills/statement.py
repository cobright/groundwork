# -*- coding: utf-8 -*-
"""담당자 진술 쪼개기 — 파일 없이 근거를 세우는 짧은 경로.

왜 필요한가:
  보고전(한 쪽짜리 일상 보고)의 재료는 문서가 아니라 **담당자가 이미 아는 사실**이다.
  자료를 등록하고 AI 분석을 돌려 확정하는 긴 경로를 거치면 '신속함'이라는 명분이 사라진다.

원칙을 어기지 않는 이유:
  이 스킬은 **아무것도 지어내지 않는다.** 사람이 쓴 문장을 주장 단위로 '쪼개기만' 한다.
  없는 사실을 채우지도, 요약하지도, 평가하지도 않는다. 그러므로 결과는 여전히
  사람이 준 것이고, 사람이 체크해서 채택한다(AI는 제안, 확정은 사람 — 원칙 1).

AI가 없어도 동작한다:
  키가 없거나 호출이 실패하면 줄 단위로 쪼갠다. 지어내는 부분이 없으므로
  이 폴백은 품질만 낮을 뿐 안전하다. 진술 경로가 LLM에 묶이면 안 된다.
"""
from __future__ import annotations

import json
import re

from ..providers.base import Message
from ..providers.registry import get_provider

SYSTEM = (
    "당신은 문서 담당자가 구술하듯 적은 메모를, 확인 가능한 '주장' 단위로 "
    "쪼개는 일만 합니다.\n"
    "절대 규칙:\n"
    "1) 원문에 없는 사실·수치·기관명·날짜를 절대 추가하지 마십시오.\n"
    "2) 요약하거나 평가하지 마십시오. 원문의 표현을 최대한 그대로 옮깁니다.\n"
    "3) 한 항목에는 한 가지 사실만 담습니다. 두 가지가 붙어 있으면 나눕니다.\n"
    "4) 사실이 아니라 담당자의 의견·추측인 문장은 opinion 을 true 로 표시합니다.\n"
    "   (예: '~할 것 같다', '~로 보인다', '개인적으로는')\n"
    "5) 인사말·군더더기(예: '아래와 같이 보고드립니다')는 버립니다.\n"
    "반드시 아래 JSON 하나만 출력하십시오(설명·머리말 금지).\n"
    '{"claims": [{"claim": "주장 한 문장", "quote": "근거가 된 원문 조각", "opinion": false}]}'
)


def split_statement(text: str, provider_name: str | None = None) -> dict:
    """진술문을 주장 목록으로 쪼갠다. 저장하지 않는다(제안일 뿐)."""
    raw_text = (text or "").strip()
    if not raw_text:
        return {"claims": [], "model": "", "fallback": False, "reason": ""}
    try:
        provider = get_provider(provider_name, task="statement")
        out = provider.complete(
            [Message("system", SYSTEM), Message("user", raw_text)],
            temperature=0.0, max_tokens=1200,
        )
        claims = _parse(out, raw_text)
        if claims:
            return {"claims": claims, "model": getattr(provider, "model", provider.name),
                    "fallback": False, "reason": ""}
        reason = "AI가 주장을 뽑아내지 못했습니다."
    except Exception as e:
        reason = str(e)
    # 폴백: 줄/문장 단위로 쪼갠다. 지어내는 부분이 없으므로 안전하다.
    return {"claims": _split_plain(raw_text), "model": "", "fallback": True, "reason": reason}


# 문장 끝으로 볼 만한 자리(마침표·물음표 뒤 공백). 개조식 줄은 줄바꿈이 곧 경계다.
_SENT = re.compile(r"(?<=[.?!])\s+")
_BULLET = re.compile(r"^\s*[□○●▶·\-–—*\d]+[.)]?\s*")


def _split_plain(text: str) -> list[dict]:
    items: list[dict] = []
    for line in text.splitlines():
        line = _BULLET.sub("", line).strip()
        if not line:
            continue
        for s in _SENT.split(line):
            s = s.strip()
            if s:
                items.append({"claim": s, "quote": s, "opinion": False})
    return items


def _parse(raw: str, source: str) -> list[dict]:
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1 and b > a:
        s = s[a:b + 1]
    try:
        d = json.loads(s)
    except Exception:
        return []
    out = []
    for it in (d.get("claims") or []):
        if not isinstance(it, dict):
            continue
        claim = str(it.get("claim", "")).strip()
        if not claim:
            continue
        out.append({
            "claim": claim,
            "quote": str(it.get("quote", "")).strip(),
            "opinion": bool(it.get("opinion")),
        })
    return out
