# -*- coding: utf-8 -*-
"""사실확인 검토 서브에이전트.

위치(원칙): 검토자는 본문과 근거 '사이'에 선다. 근거의 진위를 판정하지 않는다.
- 확정 근거를 대조 기준선으로 삼아, 본문 문장이 근거와 일치하는지, 근거가 문장이
  말하는 범위까지 뒷받침하는지, 근거가 아예 없는지를 본다.
- 근거 자체가 흔들리면(미확정/충돌/약한 등급/오래된 기준일) 판정하지 않고
  '사람이 확인해야 한다'는 의견으로 올린다.
- 본문을 절대 고치지 않는다. 구조화된 검토의견(JSON)만 낸다.
- 다른 검토자(기술/구조/비평)와 컨텍스트를 공유하지 않는다(격리).
"""
from __future__ import annotations
import json
from ..providers.base import Message
from ..providers.registry import get_provider

SYSTEM = (
    "당신은 한국 지방자치단체 행정문서의 '사실확인' 검토자입니다. "
    "당신의 역할은 세상의 진실을 판정하는 것이 아니라, 본문 문장이 '이 업무에 등록된 근거'와 "
    "일치하는지 대조하는 것입니다. 다음 규칙을 지키십시오.\n"
    "1) 확정 근거를 대조의 기준선으로 삼습니다.\n"
    "2) 본문이 근거보다 넓게 말하거나(범위 초과), 수치·기준연도·기관명이 근거와 다르면 지적합니다.\n"
    "3) 근거가 아예 없는 사실·수치는 '근거 부족'으로 지적합니다.\n"
    "4) 근거 자체가 흔들리면(미확정/자료 충돌/낮은 신뢰등급/오래된 기준일) '자료를 사람이 확인해야 함'으로 올립니다. "
    "절대로 '이 자료는 틀렸다'고 단정하지 마십시오.\n"
    "5) 본문을 고쳐 쓰지 마십시오. 수정 제안은 참고로만 제시하고, 반영은 사용자가 결정합니다.\n"
    "6) 문제가 없으면 빈 목록을 반환합니다. 억지로 만들지 마십시오.\n"
    "반드시 아래 JSON 스키마 하나만 출력하십시오(설명·머리말 금지).\n"
    '{"opinions": [{'
    '"severity": "중대|중요|일반|참고", '
    '"target_text": "문제가 된 본문 조각(짧게)", '
    '"problem": "무엇이 근거와 어떻게 어긋나는가", '
    '"suggestion": "근거 범위에 맞춘 수정 방향(참고)", '
    '"basis": "어떤 근거(E-번호)나 상태에 비추어 판단했는가", '
    '"needs": "필요한 조치(담당부서 확인/최신자료 확인 등, 없으면 빈 문자열)"'
    "}]}"
)


def review_facts(title: str, number: str, body: str, evidences: list[dict],
                 provider_name: str | None = None) -> list[dict]:
    if not body.strip():
        return []
    provider = get_provider(provider_name)
    ev_txt = _fmt_evidence(evidences)
    user = (
        f"[목차 항목] {number} {title}\n\n"
        f"[검토 대상 본문]\n{body.strip()}\n\n"
        f"[이 목차에 연결된 근거]\n{ev_txt}\n\n"
        "위 본문을 근거와 대조해 사실확인 검토의견을 지정된 JSON 으로만 내십시오. "
        "근거로 뒷받침되는 문장은 지적하지 마십시오."
    )
    raw = provider.complete([Message("system", SYSTEM), Message("user", user)],
                            temperature=0.1, max_tokens=1800)
    data = _parse(raw)
    model = getattr(provider, "model", provider.name)
    out = []
    for o in data.get("opinions", []):
        if not isinstance(o, dict):
            continue
        problem = str(o.get("problem", "")).strip()
        if not problem:
            continue
        out.append({
            "kind": "사실확인",
            "severity": _sev(o.get("severity")),
            "target_text": str(o.get("target_text", "")).strip(),
            "problem": problem,
            "suggestion": str(o.get("suggestion", "")).strip(),
            "basis": str(o.get("basis", "")).strip(),
            "needs": str(o.get("needs", "")).strip(),
            "source": "AI",
            "model": model,
        })
    return out


def _fmt_evidence(evidences: list[dict]) -> str:
    if not evidences:
        return "(연결된 근거 없음 — 본문의 사실은 대부분 '근거 부족'으로 보아야 함)"
    lines = []
    for i, e in enumerate(evidences, 1):
        state = e.get("state", "")
        mark = "확정" if state == "사용자 확정" else ("미확정" if state else "근거자료 없음")
        src = (e.get("resource_name") or "근거 없음").strip()
        summary = (e.get("resource_summary") or "").strip()
        flags = []
        if state and state != "사용자 확정":
            flags.append("미확정")
        if e.get("source_changed"):
            flags.append("자료 변경됨")
        if (e.get("status") or "") in ("충돌", "사용 보류", "추정"):
            flags.append(e["status"])
        flag_txt = (" [주의: " + ", ".join(flags) + "]") if flags else ""
        line = f"E-{i:03d} [{mark}]{flag_txt} 주장: {(e.get('claim') or '').strip()} / 자료: {src}"
        if summary:
            line += f"\n     자료요약: {summary}"
        lines.append(line)
    return "\n".join(lines)


def _sev(v) -> str:
    v = str(v or "").strip()
    return v if v in ("중대", "중요", "일반", "참고") else "일반"


def _parse(raw: str) -> dict:
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
        return d if isinstance(d, dict) else {"opinions": []}
    except Exception:
        return {"opinions": []}
