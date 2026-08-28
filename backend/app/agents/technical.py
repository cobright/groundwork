# -*- coding: utf-8 -*-
"""기술검토 서브에이전트 — 사업이 실제로 추진 가능한가.

원칙:
- AI는 전문기술자를 대신하지 않는다. 정확한 공사비·구조안전·법률판단은
  단정하지 말고 '담당부서/전문가/법률 검토 필요'로 한계를 명시한다.
- 본문을 고치지 않고 검토의견(JSON)만 낸다.
- 다른 검토자와 컨텍스트를 공유하지 않는다.
"""
from __future__ import annotations
from ..providers.base import Message
from ..providers.registry import get_provider
from .common import parse_opinions, normalize

SYSTEM = (
    "당신은 한국 지방자치단체 행정문서의 '기술검토' 검토자입니다. "
    "이 사업이 실제로 추진 가능한지를 점검합니다. 다음을 봅니다: "
    "사업비·재원의 정합성, 인허가·행정절차의 누락, 추진일정의 현실성, "
    "운영주체·유지관리, 공유재산·소유관계 절차. 규칙:\n"
    "1) 당신은 전문기술자가 아닙니다. 정확한 공사비·구조안전·법령 적합성은 "
    "단정하지 말고 '담당부서 확인 필요' 또는 '전문가/법률 검토 필요'로 needs 에 적으십시오.\n"
    "2) 사실의 근거 부족은 사실확인 검토자의 몫이므로 중복해서 지적하지 마십시오. "
    "당신은 '실행 가능성'에 집중합니다.\n"
    "3) 본문을 고쳐 쓰지 마십시오. 수정 제안은 참고로만 제시합니다.\n"
    "4) 문제가 없으면 빈 목록을 반환합니다.\n"
    "반드시 아래 JSON 하나만 출력(설명 금지):\n"
    '{"opinions":[{"severity":"중대|중요|일반|참고","target_text":"관련 본문 조각",'
    '"problem":"실행 가능성 측면의 문제","suggestion":"보완 방향(참고)",'
    '"basis":"무엇에 비추어 판단했는가","needs":"필요한 조치(담당부서/전문가/법률 확인 등)"}]}'
)


def review_technical(scope_label: str, content: str, provider_name: str | None = None) -> list[dict]:
    if not content.strip():
        return []
    provider = get_provider(provider_name)
    user = (
        f"[검토 범위] {scope_label}\n\n[검토 대상 본문]\n{content.strip()}\n\n"
        "위 내용을 '실행 가능성' 관점에서 기술검토하여 지정된 JSON 으로만 내십시오."
    )
    raw = provider.complete([Message("system", SYSTEM), Message("user", user)], temperature=0.15, max_tokens=1800)
    model = getattr(provider, "model", provider.name)
    return [x for x in (normalize(o, "기술검토", model) for o in parse_opinions(raw)) if x]
