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
    "당신은 한국 지방자치단체의 행정문서 작성을 돕는 자료분석 보조자입니다. "
    "주어진 자료의 '실제 내용 안에서만' 분석합니다. 자료에 없는 사실·수치·기관명을 "
    "추측하거나 지어내지 마십시오. 불확실하면 cautions 에 그 점을 적습니다. "
    "반드시 아래 JSON 스키마 하나만 출력하고, 그 외 설명·머리말·마크다운을 붙이지 마십시오.\n"
    '{"summary": "핵심 요약 2~3문장", '
    '"key_points": ["자료의 주요 내용·수치 항목", "..."], '
    '"usable_for": ["이 자료로 뒷받침할 수 있는 주장이나 활용 가능한 목차", "..."], '
    '"cautions": ["기준연도·출처·확정 여부 등 주의사항", "..."]}'
)


def analyze_resource(name: str, kind: str, source_org: str, base_date: str, text: str,
                     provider_name: str | None = None) -> dict:
    """자료 한 건을 분석해 구조화된 dict 를 돌려준다. 확정은 하지 않는다(사용자 몫)."""
    provider = get_provider(provider_name)
    meta = f"[자료명] {name}\n[유형] {kind}\n[작성기관] {source_org}\n[기준일] {base_date}"
    body = text.strip()
    if len(body) > 12000:          # 초기 버전: 지나치게 긴 자료는 앞부분만
        body = body[:12000] + "\n...(이하 생략)"
    user = f"{meta}\n\n[자료 본문]\n{body}\n\n위 자료를 분석해 지정된 JSON 으로만 답하십시오."
    raw = provider.complete([Message("system", SYSTEM), Message("user", user)],
                            temperature=0.1, max_tokens=1500)
    data = _parse_json(raw)
    # 스키마 방어: 누락 필드 채우고 타입 보정
    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_points": _as_list(data.get("key_points")),
        "usable_for": _as_list(data.get("usable_for")),
        "cautions": _as_list(data.get("cautions")),
        "model": getattr(provider, "model", provider.name),
    }


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
