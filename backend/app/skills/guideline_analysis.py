# -*- coding: utf-8 -*-
"""가이드라인 분석 ② — 규칙이 뽑아 놓은 것을 **판정하고 다듬는** 일만 한다.

무엇을 맡기고 무엇을 안 맡기는가:
  맡긴다  · 각주·지시문 후보가 '구해 와야 할 자료'인지, 그냥 용어 설명인지 판정
          · "인구 현황" 같은 뭉뚱그린 말을 부서에 그대로 보낼 문구로 다듬기
          · 소관 부서 추정 (있는 부서 목록 중에서만)
          · 집필카드의 '핵심 질문' 만들기
  안 맡긴다 · 목차를 짓는 일 (규칙이 문서에서 읽어 온다)
          · 없는 자료를 상상해 보태는 일 (원칙 2)

왜 문서를 통째로 넣지 않는가:
  44쪽 43,000자를 매번 밀어 넣으면 비싸고 자주 실패한다. 규칙이 이미 목차와
  후보를 다 뽑아 놓았으므로, **뼈대만** 12항목씩 끊어 보낸다. 그래서 싸고 안전하다.

AI 없이도 동작한다:
  키가 없거나 호출이 실패하면 규칙이 뽑은 후보를 그대로 쓴다. 문구가 거칠 뿐
  지어낸 것이 없으므로 안전하다. 담당자 진술의 폴백과 같은 이유다 — 없애지 말 것.
"""
from __future__ import annotations

import json
import re

from ..providers.base import Message
from ..providers.registry import get_provider

CHUNK = 12          # 한 번에 보낼 목차 항목 수

SYSTEM = (
    "당신은 공모·지원사업에 신청하는 담당자(지자체·기관·기업 등)가 계획서를 쓰기 전에, 공모 가이드라인에서 "
    "'각 항목에 무엇을 쓰고 어떤 자료를 구해야 하는지'를 정리하는 일을 돕습니다.\n"
    "입력은 가이드라인에서 **이미 뽑아낸** 목차 항목과 그 항목에 딸린 안내문·자료후보입니다.\n"
    "절대 규칙:\n"
    "1) 자료를 지어내지 마십시오. 반드시 주어진 후보(cands)나 안내문(instr)에 근거해야 합니다.\n"
    "   근거가 된 후보의 번호를 from 에 적습니다. 안내문에서 끌어냈으면 from 을 -1 로 둡니다.\n"
    "2) 후보가 '구해 와야 할 자료'가 아니라 용어 설명·주의사항이면 **버리십시오**.\n"
    "   (예: '정비지구는 …을 목적으로 한다' → 설명이므로 버림)\n"
    "3) need 는 담당 부서에 그대로 보낼 수 있게 씁니다. 무엇을·언제 기준으로·어느 단위로 인지\n"
    "   가 드러나야 합니다. ('인구 통계'(X) → '읍·면별 인구수와 최근 5년 인구증감률(주민등록 기준)'(O))\n"
    "4) dept 는 주어진 부서 목록에 있는 이름만 씁니다. 확신이 없으면 빈 문자열로 두십시오.\n"
    "   부서 목록에 없는 이름을 지어내지 마십시오.\n"
    "5) question 은 그 항목에서 답해야 할 핵심 질문 한 문장입니다. 안내문에 근거해 씁니다.\n"
    "6) length 는 가이드라인이 분량을 정했을 때만 적습니다(예: '2쪽 이내'). 없으면 빈 문자열.\n"
    "반드시 아래 JSON 하나만 출력하십시오(설명·머리말·코드펜스 금지).\n"
    '{"items":[{"id":0,"question":"","purpose":"","length":"",'
    '"needs":[{"need":"","why":"","dept":"","from":0}]}]}'
)


def _payload(items: list[dict], depts: list[str]) -> str:
    out = []
    for it in items:
        out.append({
            "id": it["id"],
            "path": it["path"],
            "instr": (it.get("instr") or "")[:700],
            "cands": [c[:200] for c in (it.get("cands") or [])][:8],
        })
    return json.dumps({"부서목록": depts, "항목": out}, ensure_ascii=False)


def _parse(raw: str) -> list[dict]:
    s = (raw or "").strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return []
    try:
        data = json.loads(s[a:b + 1])
    except json.JSONDecodeError:
        return []
    items = data.get("items")
    return items if isinstance(items, list) else []


def refine(items: list[dict], departments: list[str],
           provider_name: str | None = None) -> dict:
    """규칙이 뽑은 항목 목록을 다듬는다.

    items 각 원소: {id, path, instr, cands:[str]}
    돌려주는 것: {"by_id": {id: {question, purpose, length, needs:[{need,why,dept,from}]}},
                 "model": ..., "fallback": bool, "reason": ...}
    """
    if not items:
        return {"by_id": {}, "model": "", "fallback": False, "reason": ""}

    by_id: dict[int, dict] = {}
    model, reason, failed = "", "", 0
    try:
        provider = get_provider(provider_name, task="guideline_analysis")
        model = getattr(provider, "model", provider.name)
    except Exception as e:
        return {"by_id": _fallback(items), "model": "", "fallback": True, "reason": str(e)}

    for k in range(0, len(items), CHUNK):
        group = items[k:k + CHUNK]
        try:
            out = provider.complete(
                [Message("system", SYSTEM), Message("user", _payload(group, departments))],
                temperature=0.0, max_tokens=3000,
            )
            parsed = _parse(out)
        except Exception as e:
            parsed, reason = [], reason or str(e)
        if not parsed:
            failed += 1
            by_id.update(_fallback(group))
            continue
        got = {int(x.get("id", -1)): x for x in parsed if isinstance(x, dict)}
        for it in group:
            x = got.get(it["id"])
            by_id[it["id"]] = _clean_one(x, it) if x else _fallback([it])[it["id"]]

    fallback = failed > 0
    if fallback and not reason:
        reason = "AI 응답을 읽지 못한 묶음이 있어 그 부분은 원문 그대로 두었습니다."
    return {"by_id": by_id, "model": model, "fallback": fallback, "reason": reason}


def _clean_one(x: dict, it: dict) -> dict:
    cands = it.get("cands") or []
    needs = []
    for n in (x.get("needs") or []):
        if not isinstance(n, dict):
            continue
        text = str(n.get("need") or "").strip()
        if not text:
            continue
        try:
            src = int(n.get("from", -1))
        except (TypeError, ValueError):
            src = -1
        needs.append({
            "need": text[:300],
            "why": str(n.get("why") or "").strip()[:200],
            "dept": str(n.get("dept") or "").strip()[:40],
            "from": src if 0 <= src < len(cands) else -1,
        })
    return {
        "question": str(x.get("question") or "").strip()[:200],
        "purpose": str(x.get("purpose") or "").strip()[:200],
        "length": str(x.get("length") or "").strip()[:40],
        "needs": needs,
    }


def _fallback(items: list[dict]) -> dict:
    """AI 없이: 규칙이 뽑은 후보를 그대로 쓴다. 지어낸 것이 없으므로 안전하다."""
    out = {}
    for it in items:
        cands = it.get("cands") or []
        out[it["id"]] = {
            "question": "", "purpose": "", "length": "",
            "needs": [{"need": c[:300], "why": "", "dept": "", "from": i}
                      for i, c in enumerate(cands)],
        }
    return out
