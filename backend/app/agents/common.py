# -*- coding: utf-8 -*-
"""검토 서브에이전트 공통 도구.
모든 검토자는 같은 JSON 계약을 지키고, 본문을 고치지 않는다.
"""
from __future__ import annotations
import json


def parse_opinions(raw: str) -> list:
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
        ops = d.get("opinions", []) if isinstance(d, dict) else []
        return ops if isinstance(ops, list) else []
    except Exception:
        return []


def sev(v) -> str:
    v = str(v or "").strip()
    return v if v in ("중대", "중요", "일반", "참고") else "일반"


def normalize(o: dict, kind: str, model: str) -> dict | None:
    if not isinstance(o, dict):
        return None
    problem = str(o.get("problem", "")).strip()
    if not problem:
        return None
    return {
        "kind": kind,
        "severity": sev(o.get("severity")),
        "target_text": str(o.get("target_text", "")).strip(),
        "problem": problem,
        "suggestion": str(o.get("suggestion", "")).strip(),
        "basis": str(o.get("basis", "")).strip(),
        "needs": str(o.get("needs", "")).strip(),
        "source": "AI",
        "model": model,
    }


# 문서 전체 검토용: 목차별 본문을 하나의 텍스트로 모은다.
MAX_DOC_CHARS = 12000     # 자료분석 스킬과 같은 기준. 너무 긴 문서는 앞부분만 검토한다.


def assemble_document(sections: list[dict], limit: int = MAX_DOC_CHARS) -> tuple[str, bool]:
    """sections: [{number, title, body}] → (이어붙인 전체 본문, 잘렸는지 여부).

    문서가 길면 모델의 입력 한도를 넘어 실패하거나 비용이 급증하므로 앞부분만 보낸다.
    잘렸다는 사실은 숨기지 않고 본문 끝과 반환값 양쪽에 남겨 사용자에게 알린다.
    """
    parts = []
    for s in sections:
        body = (s.get("body") or "").strip()
        head = f"{s.get('number','')} {s.get('title','')}".strip()
        parts.append(f"## {head}\n{body if body else '(본문 없음)'}")
    text = "\n\n".join(parts)
    if len(text) > limit:
        return text[:limit] + "\n\n...(문서가 길어 이하 생략 — 앞부분만 검토합니다)", True
    return text, False
