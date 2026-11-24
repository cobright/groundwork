# -*- coding: utf-8 -*-
"""초고 작성 스킬 — 선택한 목차 하나를, 연결된 확정 근거와 집필카드 안에서만 쓴다.

설계 4단계 원칙:
- 근거 없는 내용은 지어내지 않고 [확인 필요: ...] 로 남긴다.
- 사업비·수요 등 수치를 상상해 만들지 않는다.
- 결과는 '제안'일 뿐, 자동으로 본문에 반영하지 않는다(사용자 몫).
- 강도(엄격/유연/자료목록)를 사용자가 목차마다 고를 수 있다.
"""
from __future__ import annotations
from ..providers.base import Message
from ..providers.registry import get_provider
from ..services.evidence import evidence_mark, STATEMENT_KIND

_COMMON = (
    "당신은 한국의 공공·기관 문서(행정기관의 계획서·보고서, 지원사업 신청서 등) 초고를 돕는 보조자입니다. "
    "지금 문서의 목차 항목 '하나'에 대한 초고만 작성합니다. "
    "제공된 '집필카드'와 '확정 근거'에 있는 사실만 사용하십시오. "
    "과장·단정·홍보성 표현을 피합니다."
)

# 문체는 근거 취급 규칙(_RULES)과 별개의 축이다.
# 무엇을 쓸 수 있는가(_RULES)와 어떤 모양으로 쓰는가(_STYLE)는 서로 간섭하지 않는다.
_STYLE = {
    "계획서": (
        "문체(계획서):\n"
        "- 공문서·보고서 문체. 짧은 서술 또는 개조식.\n"
        "- 지정된 분량에 맞춥니다."
    ),
    "보고전": (
        "문체(보고전 — 한 쪽짜리 일상 보고):\n"
        "- 개조식만 씁니다. 줄머리는 ○ 를 쓰고, 하위는 두 칸 들여 - 를 씁니다.\n"
        "- 한 줄에 한 가지 사실만 담고, 서술형 어미(…입니다/…하였습니다)를 쓰지 않습니다. "
        "'현황 파악 완료'처럼 명사형으로 끊습니다.\n"
        "- 지정된 분량(줄 수)을 반드시 지킵니다. 넘치면 덜 중요한 줄을 버립니다.\n"
        "- 수식어를 넣지 않습니다. 상급자가 30초 안에 읽습니다."
    ),
}

_RULES = {
    "엄격": (
        "규칙(엄격):\n"
        "- 확정 근거에 있는 내용만 문장으로 씁니다.\n"
        "- 근거가 없는 사실·수치·기관명·일정은 절대 만들지 말고, 그 자리에 "
        "[확인 필요: 무엇이 필요한지] 형태로 남깁니다.\n"
        "- 근거로 뒷받침되는 문장 끝에는 (근거: E-번호) 처럼 근거 번호를 답니다.\n"
        "- 매끄러움보다 정확성이 우선입니다."
    ),
    "유연": (
        "규칙(유연):\n"
        "- 확정 근거의 사실을 중심으로 쓰되, 문단을 잇는 연결문장은 작성해도 됩니다.\n"
        "- 근거를 넘어서는 판단·추정은 문장 앞에 [추정] 을 붙여 반드시 구분합니다.\n"
        "- 근거가 없는 핵심 사실·수치는 지어내지 말고 [확인 필요: ...] 로 남깁니다.\n"
        "- 근거로 뒷받침되는 문장 끝에는 (근거: E-번호) 를 답니다."
    ),
    "자료목록": (
        "규칙(자료목록만):\n"
        "- 본문을 쓰지 말고, 이 목차를 제대로 쓰려면 어떤 자료·근거가 더 필요한지 "
        "'필요한 자료 목록'만 항목으로 제시합니다.\n"
        "- 이미 확정 근거로 확보된 부분은 '확보됨'으로 짧게 표시합니다."
    ),
}


def write_draft(card: dict, evidences: list[dict], title: str, number: str,
                strictness: str = "엄격", provider_name: str | None = None,
                family: str = "계획서") -> dict:
    """목차 하나의 초고(제안)를 생성한다. 본문에 자동 반영하지 않는다."""
    provider = get_provider(provider_name, task="draft_brief" if family == "보고전" else "draft_plan")
    rules = _RULES.get(strictness, _RULES["엄격"])
    style = _STYLE.get(family, _STYLE["계획서"])

    # 확정 전엔 근거가 아니다(원칙 2). 본문을 쓰는 모드에서는 확정 자료와 채택한 진술만 넘긴다 —
    # 예전엔 미확정 근거도 [미확정] 표시만 달아 함께 넘겼다(2026-11-24 기능 분석에서 짚음).
    # '자료목록' 모드는 무엇이 더 필요한지 말하는 일이라, 미확정 근거도 '확정 필요'로 보이게 둔다.
    excluded = []
    if strictness != "자료목록":
        usable = [e for e in evidences if evidence_mark(e) in ("확정", "진술")]
        excluded = [{"ev_no": e.get("ev_no", ""), "claim": (e.get("claim") or "")[:60], "mark": evidence_mark(e)}
                    for e in evidences if e not in usable]
        evidences = usable

    card_txt = _fmt_card(card)
    ev_txt = _fmt_evidence(evidences)
    has_conf = any(e.get("state") == "사용자 확정" for e in evidences)
    has_stmt = any(e.get("resource_kind") == STATEMENT_KIND for e in evidences)

    user = (
        f"[목차 항목] {number} {title}\n\n"
        f"[집필카드]\n{card_txt}\n\n"
        f"[이 목차에 연결된 확정 근거]\n{ev_txt}\n\n"
        + ("주의: 확정된 근거가 없습니다. 근거가 필요한 내용은 지어내지 말고 "
           "[확인 필요: ...] 로만 남기십시오.\n\n" if not has_conf else "")
        + ("주의: [진술] 로 표시된 것은 담당자가 직접 말한 사실이며 문서로 확인된 자료가 아닙니다. "
           "그 내용을 쓰는 것은 되지만, 문서·통계에서 확인된 것처럼 단정하지 마십시오.\n\n"
           if has_stmt else "")
        + "위 재료만으로 이 목차의 초고를 작성하십시오. 재료 밖의 사실을 추가하지 마십시오."
    )
    text = provider.complete(
        [Message("system", _COMMON + "\n\n" + style + "\n\n" + rules), Message("user", user)],
        temperature=0.2, max_tokens=600 if family == "보고전" else 1800,
    ).strip()
    return {"ai_suggestion": text, "strictness": strictness, "family": family,
            "model": getattr(provider, "model", provider.name),
            "used_confirmed_evidence": has_conf, "excluded": excluded}


def _fmt_card(card: dict) -> str:
    if not card:
        return "(집필카드 없음)"
    rows = [
        ("작성 목적", card.get("purpose")),
        ("핵심 질문", card.get("question")),
        ("핵심 메시지", card.get("message")),
        ("반드시 포함할 내용", card.get("content")),
        ("분량", card.get("length")),   # 보고전에서는 분량이 곧 형식이다
    ]
    out = [f"- {k}: {v}" for k, v in rows if (v or "").strip()]
    return "\n".join(out) or "(집필카드 내용 없음)"


def _fmt_evidence(evidences: list[dict]) -> str:
    if not evidences:
        return "(연결된 근거 없음)"
    lines = []
    for i, e in enumerate(evidences, 1):
        tag = e.get("ev_no") or ("E-%03d" % i)   # 번호는 근거표·부록과 같은 것을 쓴다
        mark = evidence_mark(e)                  # 진술을 확정 자료로 위장하지 않는다
        claim = (e.get("claim") or "").strip()
        src = (e.get("resource_name") or "근거 없음").strip()
        loc = (e.get("locator") or "").strip()
        summary = (e.get("resource_summary") or "").strip()
        line = f"{tag} [{mark}] 주장: {claim} / 근거자료: {src}{(' ' + loc) if loc else ''}"
        # 진술은 요약이 진술문 전체라 근거마다 통째로 반복된다. 인용(locator)이 이미
        # 정확한 출처이므로 요약은 붙이지 않는다.
        if summary and mark != "진술":
            line += f"\n     자료요약: {summary}"
        lines.append(line)
    return "\n".join(lines)
