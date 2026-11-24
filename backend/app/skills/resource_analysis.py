# -*- coding: utf-8 -*-
"""자료분석 스킬 — 반복되는 '자료 한 건 분석' 절차를 표준화한다.

원칙(설계 2단계):
- AI는 등록된 자료 '안에서만' 요약한다. 없는 내용을 지어내지 않는다.
- 결과는 참고일 뿐, 사용자가 확정해야 근거표의 공식 근거가 된다.
- 반드시 구조화된 JSON 으로만 답하게 하여 하네스가 파싱/통제할 수 있게 한다.
"""
from __future__ import annotations
import json
from ..providers.base import Message
from ..providers.registry import get_provider

SYSTEM = (
    "당신은 한국의 공공·기관 문서(행정기관의 계획서·보고서, 지원사업 신청서 등) 작성을 돕는 자료분석 보조자입니다. "
    "주어진 자료의 '실제 내용 안에서만' 분석합니다. 자료에 없는 사실·수치·기관명을 "
    "추측하거나 지어내지 마십시오. 불확실하면 cautions 에 그 점을 적습니다. "
    "수치가 있으면 key_points 에 연도·단위와 함께 그대로 옮겨 적으십시오(반올림·추정 금지). "
    "반드시 아래 JSON 스키마 하나만 출력하고, 그 외 설명·머리말·마크다운을 붙이지 마십시오.\n"
    '{"summary": "핵심 요약 2~3문장", '
    '"key_points": ["자료의 주요 내용·수치 항목", "..."], '
    '"usable_for": ["이 자료로 뒷받침할 수 있는 주장이나 활용 가능한 목차", "..."], '
    '"cautions": ["기준연도·출처·확정 여부 등 주의사항", "..."], '
    '"claims": [{"claim": "이 자료로 세울 수 있는 주장 한 문장", '
    '"quote": "그 주장을 받치는 자료 본문 구간(글자 그대로)", "answers": "답하는 요청 항목(없으면 빈 글자)"}]}\n'
    "claims 규칙: 최대 8개. quote 는 자료 본문에서 **한 글자도 바꾸지 말고** 복사한 한두 문장 또는 표 한 줄입니다"
    "(요약·의역·줄임표 금지). 본문에서 그대로 옮길 구간이 없으면 그 주장은 내놓지 마십시오. "
    "claim 은 quote 에 있는 사실만 말합니다."
)

# 부서 회신 자료일 때 덧붙이는 규칙.
# 담당자가 대신 하기 어려운 일은 '요약'이 아니라 **요청한 것 중 빠진 것 찾기**다.
# 세부사업계획서 40쪽을 받아 놓고 정작 요청한 수치가 없다는 것은, 초고를 쓰다가
# 뒤늦게 알게 되는 것이 가장 비싸다.
ASKED_RULE = (
    "\n이 자료는 다른 부서에 요청해서 받은 회신 자료입니다. 무엇을 요청했는지가 함께 주어집니다. "
    "요청한 항목 하나하나에 대해 이 자료에 답이 있는지 확인하십시오.\n"
    "- 답이 있으면 key_points 맨 앞에 '요청한 ○○: (자료에 적힌 값 그대로)' 로 적습니다.\n"
    "- 답이 없으면 cautions 맨 앞에 '요청한 ○○은(는) 이 자료에 없습니다 — 추가 요청 필요' 로 적습니다. "
    "비슷해 보이는 다른 수치로 대신하거나 채워 넣지 마십시오.\n"
    "- 요청하지 않았지만 문서를 쓸 때 쓸모 있어 보이는 내용은 usable_for 에 적습니다.\n"
    "- 요청한 항목에 답하는 claims 를 먼저 내고, answers 에 그 요청 항목을 적습니다."
)


# ASKED_RULE 이 정한 문구. 이 글자로 '요청한 것이 회신에 없다'를 알아본다(문구를 바꾸면 여기도 함께).
MISSING_MARK = "이 자료에 없습니다"


def asked_missing(cautions) -> list[str]:
    """분석 주의사항 중 '요청한 ○○은(는) 이 자료에 없습니다' 줄만. 회신이 요청과 다른지 가르는 데 쓴다.

    2026-11-24 실제 업무(#6)에서 요청과 전혀 다른 파일이 회신으로 등록됐다. AI 는 이 문구로 정확히
    알렸지만 주의사항 목록의 한 줄에 묻혀 그대로 확정되고, 최종본 부록에 요청 이름으로 ✔ 가 찍혔다.
    """
    return [c for c in (cautions or []) if isinstance(c, str) and c.startswith("요청한") and MISSING_MARK in c]


def analyze_resource(name: str, kind: str, source_org: str, base_date: str, text: str,
                     provider_name: str | None = None, asked: str = "") -> dict:
    """자료 한 건을 분석해 구조화된 dict 를 돌려준다. 확정은 하지 않는다(사용자 몫).

    asked: 이 자료가 부서 회신이면 '무엇을 요청했는지'. 있으면 요청 대조까지 시킨다.
    """
    provider = get_provider(provider_name, task="resource_analysis")
    meta = f"[자료명] {name}\n[유형] {kind}\n[작성기관] {source_org}\n[기준일] {base_date}"
    if asked.strip():
        meta += f"\n[요청한 내용] {asked.strip()}"
    body = text.strip()
    if len(body) > 12000:          # 초기 버전: 지나치게 긴 자료는 앞부분만
        body = body[:12000] + "\n...(이하 생략)"
    user = f"{meta}\n\n[자료 본문]\n{body}\n\n위 자료를 분석해 지정된 JSON 으로만 답하십시오."
    system = SYSTEM + (ASKED_RULE if asked.strip() else "")
    # 주장 후보(인용 포함)가 붙어 출력이 길어졌다 — 1500 이면 JSON 이 잘려 통째로 못 읽는다.
    raw = provider.complete([Message("system", system), Message("user", user)],
                            temperature=0.1, max_tokens=2600)
    data = _parse_json(raw)
    # 스키마 방어: 누락 필드 채우고 타입 보정
    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_points": _as_list(data.get("key_points")),
        "usable_for": _as_list(data.get("usable_for")),
        "cautions": _as_list(data.get("cautions")),
        "claims": _as_claims(data.get("claims")),
        "model": getattr(provider, "model", provider.name),
    }


def _as_claims(v) -> list[dict]:
    """주장 후보를 {claim, quote, answers} 로 고른다. 인용이 원문에 있는지는 여기서 보지 않는다 —
    자료 본문이 나중에 바뀔 수 있으므로 읽을 때마다 `services/quote.py` 로 다시 본다."""
    out = []
    for x in v if isinstance(v, list) else []:
        if not isinstance(x, dict):
            continue
        claim = str(x.get("claim") or "").strip()
        if not claim:
            continue
        out.append({"claim": claim[:300], "quote": str(x.get("quote") or "").strip()[:600],
                    "answers": str(x.get("answers") or "").strip()[:120]})
    return out[:8]


def _parse_json(raw: str) -> dict:
    s = raw.strip()
    # ```json ... ``` 같은 코드펜스 제거
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    # 본문에서 첫 { 부터 마지막 } 까지만 취함
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1 and b > a:
        s = s[a:b + 1]
    try:
        return json.loads(s)
    except Exception:
        # 모델이 형식을 어겼을 때: 요약만이라도 살린다
        return {"summary": raw.strip()[:500], "cautions": ["AI 응답이 지정 형식과 달라 자동 파싱하지 못했습니다. 원문을 확인하세요."]}


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []
