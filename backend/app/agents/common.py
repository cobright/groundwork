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
def assemble_document(sections: list[dict]) -> str:
    """sections: [{number, title, body}] → 번호·제목과 함께 이어붙인 전체 본문."""
    parts = []
    for s in sections:
        body = (s.get("body") or "").strip()
        head = f"{s.get('number','')} {s.get('title','')}".strip()
        parts.append(f"## {head}\n{body if body else '(본문 없음)'}")
    return "\n\n".join(parts)
