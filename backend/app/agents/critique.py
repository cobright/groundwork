# -*- coding: utf-8 -*-
"""비평 서브에이전트 — 작성자와 다른 입장에서 가장 약한 곳을 찌른다.

원칙:
- 지정된 '관점'(군수/예산부서/평가위원 등)에 서서, 그 사람이 던질 가장 곤란한
  질문과 가장 약한 지점을 찾는다.
- 본문을 고치지 않고 검토의견(JSON)만 낸다. 관점을 basis 에 명시한다.
"""
from __future__ import annotations
from ..providers.base import Message
from ..providers.registry import get_provider
from .common import parse_opinions, normalize

PERSPECTIVES = {
    "군수": "군수(최종 결정권자). '지금 무엇을 결정해 달라는 것인가, 왜 지금 해야 하는가, 실패하면 무엇이 문제인가, 다른 사업보다 우선인가'를 따진다.",
    "예산부서": "예산부서. '재원은 어디서 확보하는가, 운영비는 얼마인가, 사업비 증가 위험은, 기존 사업과 중복은 없는가'를 따진다.",
    "사업부서": "실제 집행 사업부서. '누가 실무를 맡는가, 인허가·협의기간은 반영됐는가, 선정 후 실제 추진 가능한가, 운영주체는 명확한가'를 따진다.",
    "평가위원": "공모 평가위원. '이 지역만의 필요성이 드러나는가, 사업이 문제 해결과 연결되는가, 근거가 구체적인가, 계획이 지나치게 낙관적이지 않은가'를 따진다.",
    "의회": "의회. '주민에게 어떤 이익인가, 특혜·형평성 문제는 없는가, 예산 대비 효과는, 사후 관리는 되는가'를 따진다.",
}

SYSTEM_TMPL = (
    "당신은 한국 지방자치단체 행정문서를 '{persp_name}'의 입장에서 비평하는 검토자입니다. "
    "관점: {persp_desc}\n"
    "작성자와 다른 입장에서, 이 문서의 가장 약한 지점과 가장 곤란한 질문을 찾으십시오. 규칙:\n"
    "1) 그 관점에서 실제로 나올 법한 날카로운 지적에 집중합니다(칭찬은 불필요).\n"
    "2) 사실·수치 오류(사실확인)나 순수 논리배치(구조검토)와 겹치면 생략하고, "
    "'설득력·우선순위·위험·형평성' 같은 판단 지점을 우선하십시오.\n"
    "3) 본문을 고쳐 쓰지 마십시오.\n"
    "4) basis 에 어느 관점의 지적인지 밝히십시오. 문제가 없으면 빈 목록.\n"
    "반드시 아래 JSON 하나만 출력(설명 금지):\n"
    '{{"opinions":[{{"severity":"중대|중요|일반|참고","target_text":"관련 부분",'
    '"problem":"이 관점에서 본 약점/곤란한 질문","suggestion":"보완하면 좋을 방향",'
    '"basis":"{persp_name} 관점","needs":""}}]}}'
)


def review_critique(scope_label: str, content: str, perspective: str = "군수",
                    provider_name: str | None = None) -> list[dict]:
    if not content.strip():
        return []
    persp_desc = PERSPECTIVES.get(perspective, PERSPECTIVES["군수"])
    provider = get_provider(provider_name, task="review_critique")
    system = SYSTEM_TMPL.format(persp_name=perspective, persp_desc=persp_desc)
    user = (
        f"[검토 범위] {scope_label}\n\n[검토 대상 본문]\n{content.strip()}\n\n"
        f"위 내용을 '{perspective}' 관점에서 비평하여 지정된 JSON 으로만 내십시오."
    )
    raw = provider.complete([Message("system", system), Message("user", user)], temperature=0.3, max_tokens=1800)
    model = getattr(provider, "model", provider.name)
    return [x for x in (normalize(o, "비평", model) for o in parse_opinions(raw)) if x]
