# -*- coding: utf-8 -*-
"""구조검토 서브에이전트 — 논리가 결론까지 이어지는가.

원칙:
- 문장 교정이 아니라 문서의 뼈대를 본다: 문제–원인–대안–권고의 연결,
  목적과 결론의 일치, 중복·누락, 목차별 역할, 평가항목 대응.
- 문서 전체를 볼 때 제 역할을 한다(목차별로도 실행은 가능).
- 본문을 고치지 않고 검토의견(JSON)만 낸다.
"""
from __future__ import annotations
from ..providers.base import Message
from ..providers.registry import get_provider
from .common import parse_opinions, normalize

SYSTEM = (
    "당신은 한국 지방자치단체 행정문서의 '구조검토' 검토자입니다. "
    "문장 표현이 아니라 '논리 구조'를 봅니다: 문서 목적과 결론의 일치, "
    "문제–원인–대안–권고의 연결, 목차 간 중복·누락, 각 목차의 역할이 분명한지, "
    "결론에 이르는 논리가 끊기는 지점이 어디인지. 규칙:\n"
    "1) 개별 문장의 사실·수치 문제(사실확인)나 실행 가능성(기술검토)은 중복 지적하지 마십시오. "
    "당신은 '논리의 연결과 배치'에 집중합니다.\n"
    "2) 어디에서 논리가 끊기는지 target_text 에 해당 목차/부분을 지목하십시오.\n"
    "3) 본문을 고쳐 쓰지 마십시오. 재구성 방향만 제안합니다.\n"
    "4) 문제가 없으면 빈 목록을 반환합니다.\n"
    "반드시 아래 JSON 하나만 출력(설명 금지):\n"
    '{"opinions":[{"severity":"중대|중요|일반|참고","target_text":"관련 목차/부분",'
    '"problem":"논리 구조상의 문제(끊김/중복/누락/불일치)","suggestion":"구성 보완 방향",'
    '"basis":"어떤 흐름에 비추어 판단했는가","needs":""}]}'
)


def review_structure(scope_label: str, content: str, provider_name: str | None = None) -> list[dict]:
    if not content.strip():
        return []
    provider = get_provider(provider_name)
    user = (
        f"[검토 범위] {scope_label}\n\n[검토 대상 본문]\n{content.strip()}\n\n"
        "위 내용을 '논리 구조' 관점에서 검토하여 지정된 JSON 으로만 내십시오."
    )
    raw = provider.complete([Message("system", SYSTEM), Message("user", user)], temperature=0.2, max_tokens=1800)
    model = getattr(provider, "model", provider.name)
    return [x for x in (normalize(o, "구조검토", model) for o in parse_opinions(raw)) if x]
