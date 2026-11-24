# -*- coding: utf-8 -*-
"""문서 유형별 목차 틀 — 이 앱에서 목차 템플릿의 유일한 출처.

틀의 **내용**은 `app/doc_templates/*.json` 에 있다(유형 하나에 파일 하나). 이 모듈은 그 파일들을
읽고 검사해 `DOC_TEMPLATES`·`BLOCKS` 로 내놓는 일만 한다. 코드를 모르는 사람도 파일 하나를 더하거나
고쳐서 문서 유형을 보탤 수 있게 하려고 떼어 냈다(2026-11-24). 파일 쓰는 법은 `app/doc_templates/README.md`.

왜 백엔드에 두는가:
  문서 유형(doc_type)은 '표시용 라벨'이 아니라 **동작을 가르는 값**이다.
  초고 문체(계획서=문단 / 보고전=개조식)와 목차 틀이 같은 유형에서 갈라져 나오므로
  한곳에 있어야 한다. 예전엔 목차 틀만 프런트(api.js)에 있었고 문체는 없었다.
  두 곳에 나눠 두면 유형이 늘 때마다 반드시 어긋난다.

계열(family)
  계획서 — 사업계획서·보고서 등 여러 쪽짜리. 목차를 사람이 짜고 자료를 모아 쓴다.
  보고전 — 한 쪽짜리 일상 보고. **틀이 이미 정해져 있고** 재료는 담당자가 아는 사실이다.
           그래서 빠르다. AI가 없는 사실을 지어내서 빨라지는 것이 아니다.

집필카드를 미리 채우는 이유: 문장을 대신 써 주는 것이 아니라 **빠뜨리면 감점·반려당할 것을
먼저 짚어 주는 것**이 이 도구가 여기서 주는 값이다. 근거 없는 안내문은 없느니만 못하다
(CLAUDE.md 7장 — 빈 카드를 억지로 채우지 말 것).
"""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "doc_templates"
FAMILIES = ("계획서", "보고전")

# 파일의 한국어 이름(화면의 집필카드 칸 이름과 같다) → 내부 이름
CARD_KEYS = {
    "작성 목적": "purpose",
    "핵심 질문": "question",
    "핵심 메시지": "message",
    "반드시 포함할 내용": "content",
    "분량": "length",
}
# 카드 기본값(집필카드의 빈 형태)
_CARD0 = {"purpose": "", "question": "", "message": "", "content": "", "length": "1쪽", "status": "작성 전"}


class TemplateError(ValueError):
    """틀 파일이 잘못됐다. 어느 파일의 어디가 왜 틀렸는지 말한다."""


def _node(item, where: str) -> dict:
    """파일의 항목 하나 → {"title", "children", "card"?}.

    글자 하나("기본 과업")는 카드 없는 항목이다. 카드 칸이 하나라도 있으면 카드를 만들고,
    빈 칸은 기본값으로 채운다.
    """
    if isinstance(item, str):
        if not item.strip():
            raise TemplateError(f"{where}: 빈 항목 이름이 있습니다.")
        return {"title": item.strip(), "children": []}
    if not isinstance(item, dict):
        raise TemplateError(f"{where}: 항목은 글자이거나 {{\"항목\": ...}} 묶음이어야 합니다.")
    title = str(item.get("항목", "")).strip()
    if not title:
        raise TemplateError(f"{where}: \"항목\"(이름)이 없습니다.")
    unknown = set(item) - {"항목", "하위"} - set(CARD_KEYS)
    if unknown:
        raise TemplateError(f"{where} '{title}': 모르는 칸 {sorted(unknown)}. "
                            f"쓸 수 있는 칸: 항목, 하위, {', '.join(CARD_KEYS)}")
    kids = item.get("하위", [])
    if not isinstance(kids, list):
        raise TemplateError(f"{where} '{title}': \"하위\"는 목록([ ... ])이어야 합니다.")
    node = {"title": title,
            "children": [_node(k, f"{where} > {title}") for k in kids]}
    card = {CARD_KEYS[k]: str(v) for k, v in item.items() if k in CARD_KEYS}
    if card:
        node["card"] = {**_CARD0, **{k: v for k, v in card.items() if v != ""}}
    return node


def load_templates(folder: Path = TEMPLATE_DIR) -> tuple[dict[str, dict], list[dict]]:
    """폴더의 틀 파일을 읽어 (유형 이름 → {family, nodes}, 목차안 조합 블록) 을 돌려준다.

    `_` 로 시작하는 파일은 유형이 아니다(`_목차안_조합.json`). 순서는 각 파일의 "순서" 값.
    """
    found = []
    for path in sorted(folder.glob("*.json")):
        if path.name.startswith("_"):
            continue
        where = path.name
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise TemplateError(f"{where}: JSON 문법 오류 — {e.msg} ({e.lineno}번째 줄 {e.colno}번째 칸)") from e
        if not isinstance(doc, dict):
            raise TemplateError(f"{where}: 파일 전체가 {{ ... }} 하나여야 합니다.")
        unknown = set(doc) - {"유형", "계열", "순서", "목차"}
        if unknown:
            raise TemplateError(f"{where}: 모르는 칸 {sorted(unknown)}. 쓸 수 있는 칸: 유형, 계열, 순서, 목차")
        name = str(doc.get("유형", "")).strip()
        if not name:
            raise TemplateError(f"{where}: \"유형\"(문서 유형 이름)이 없습니다.")
        family = doc.get("계열")
        if family not in FAMILIES:
            raise TemplateError(f"{where}: \"계열\"은 {' 또는 '.join(FAMILIES)} 이어야 합니다(지금: {family!r}).")
        items = doc.get("목차")
        if not isinstance(items, list) or not items:
            raise TemplateError(f"{where}: \"목차\"에 항목이 하나 이상 있어야 합니다.")
        order = doc.get("순서", 9999)
        if not isinstance(order, (int, float)):
            raise TemplateError(f"{where}: \"순서\"는 숫자여야 합니다.")
        found.append((order, where, name, family, [_node(it, where) for it in items]))

    templates: dict[str, dict] = {}
    for order, where, name, family, nodes in sorted(found, key=lambda x: (x[0], x[1])):
        if name in templates:
            raise TemplateError(f"{where}: 유형 '{name}' 이 다른 파일과 겹칩니다.")
        templates[name] = {"family": family, "nodes": nodes}

    blocks: list[dict] = []
    bpath = folder / "_목차안_조합.json"
    if bpath.exists():
        b = json.loads(bpath.read_text(encoding="utf-8-sig"))
        for blk in b.get("블록", []):
            blocks.append({"name": blk["이름"], "desc": blk.get("설명", ""),
                           "sections": [_node(s, bpath.name) for s in blk.get("항목", [])]})
    return templates, blocks


# 유형 이름 → {"family": 계열, "nodes": 목차 틀}. 앱이 뜰 때 한 번 읽는다.
# 목차안 조합 블록은 계획서 계열에서만 쓴다.
DOC_TEMPLATES, BLOCKS = load_templates()

# 이름을 바꾼 유형: 옛 이름 → 새 이름(2026-11-24, 지자체 전용 이름을 중립어로).
# db._migrate() 가 이미 만든 업무의 doc_type 을 옮길 때 쓴다. 틀 내용은 그대로다.
RENAMED_TYPES = {
    "군정기획보고서": "기획보고서",
    "군수 관심사업 추진계획서": "기관장 관심사업 추진계획서",
}


def family_of(doc_type: str) -> str:
    """문서 유형이 어느 계열인지. 모르면 '계획서'로 본다(기존 동작 유지).

    유형 이름을 그대로 못 찾을 때를 대비해 '보고전'이 앞에 붙은 것도 계열로 인정한다
    (사용자가 유형명을 직접 고쳐 쓸 수 있으므로).
    """
    t = (doc_type or "").strip()
    if t in DOC_TEMPLATES:
        return DOC_TEMPLATES[t]["family"]
    return "보고전" if t.startswith("보고전") else "계획서"
