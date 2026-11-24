# -*- coding: utf-8 -*-
"""문서 유형 파일(app/doc_templates) — 기여자가 파일을 고쳐도 앱이 깨지지 않는지, 틀렸으면 이유를 말하는지."""
import json

import pytest

from app.services.templates import (BLOCKS, DOC_TEMPLATES, TemplateError, family_of,
                                    load_templates)


def test_저장소의_모든_틀_파일이_읽힌다():
    assert "공모사업 계획서" in DOC_TEMPLATES
    assert {t["family"] for t in DOC_TEMPLATES.values()} == {"계획서", "보고전"}
    assert len(BLOCKS) == 3
    # 계획서 계열이 앞에, 보고전 계열이 뒤에(파일의 '순서')
    fams = [t["family"] for t in DOC_TEMPLATES.values()]
    assert fams == sorted(fams, key=["계획서", "보고전"].index)


def test_화면의_카드_칸_이름이_내부_이름으로_바뀐다():
    first = DOC_TEMPLATES["공모사업 계획서"]["nodes"][0]
    assert first["title"] == "추진배경"
    assert first["card"]["length"] == "0.5~1쪽"
    assert first["card"]["purpose"].startswith("심사위원이")
    assert first["card"]["status"] == "작성 전"


def test_API는_파일의_틀을_그대로_내준다(client):
    got = client.get("/api/templates").json()
    assert [t["name"] for t in got["templates"]] == list(DOC_TEMPLATES)
    assert got["blocks"] == BLOCKS


def test_계열_판정():
    assert family_of("보고전 · 상황 보고") == "보고전"
    assert family_of("공모사업 계획서") == "계획서"
    assert family_of("보고전 · 내가 고친 이름") == "보고전"
    assert family_of("") == "계획서"


def _write(folder, name, doc):
    (folder / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_새_파일_하나로_유형이_더해진다(tmp_path):
    _write(tmp_path, "01_a.json", {"유형": "창업 사업계획서", "계열": "계획서", "순서": 5,
                                   "목차": ["문제 인식", {"항목": "팀 구성", "분량": "0.5쪽"}]})
    t, blocks = load_templates(tmp_path)
    nodes = t["창업 사업계획서"]["nodes"]
    assert nodes[0] == {"title": "문제 인식", "children": []}
    assert nodes[1]["card"]["length"] == "0.5쪽" and nodes[1]["card"]["purpose"] == ""
    assert blocks == []


@pytest.mark.parametrize("doc, says", [
    ({"유형": "x", "계열": "계획서", "목차": [{"항목": "a", "작성목적": "오타"}]}, "작성목적"),
    ({"유형": "x", "계열": "보고서", "목차": ["a"]}, "계열"),
    ({"유형": "", "계열": "계획서", "목차": ["a"]}, "유형"),
    ({"유형": "x", "계열": "계획서", "목차": []}, "목차"),
    ({"유형": "x", "계열": "계획서", "목차": [{"하위": ["a"]}]}, "항목"),
])
def test_틀린_파일은_어디가_왜_틀렸는지_말한다(tmp_path, doc, says):
    _write(tmp_path, "01_틀림.json", doc)
    with pytest.raises(TemplateError) as e:
        load_templates(tmp_path)
    assert "01_틀림.json" in str(e.value) and says in str(e.value)


def test_JSON_문법_오류는_줄_번호를_말한다(tmp_path):
    (tmp_path / "01_깨짐.json").write_text('{"유형": "x",\n "계열": "계획서"\n "목차": []}', encoding="utf-8")
    with pytest.raises(TemplateError) as e:
        load_templates(tmp_path)
    assert "줄" in str(e.value)


def test_유형_이름이_겹치면_막는다(tmp_path):
    for n in ("01_a.json", "02_b.json"):
        _write(tmp_path, n, {"유형": "같은 이름", "계열": "계획서", "목차": ["a"]})
    with pytest.raises(TemplateError, match="겹칩니다"):
        load_templates(tmp_path)


def test_옛_유형_이름의_업무는_켤_때_새_이름으로_옮겨진다(client, project):
    from app import db
    from app.services.templates import RENAMED_TYPES
    with db.connect() as c:
        c.execute("UPDATE projects SET doc_type='군정기획보고서' WHERE id=?", (project,))
    db.init_db()            # 다시 켠 것과 같다
    p = client.get(f"/api/projects/{project}").json()
    p = p.get("project", p)
    assert p["doc_type"] == "기획보고서"
    assert all(new in DOC_TEMPLATES for new in RENAMED_TYPES.values())
    assert not any(old in DOC_TEMPLATES for old in RENAMED_TYPES)


def test_비평은_옛_관점_이름도_받는다(fake_ai):
    from app.agents import critique
    fp = fake_ai("[]", critique)
    critique.review_critique("전체", "본문", perspective="군수")
    system = fp.calls[0][0].content
    assert "'기관장'" in system and "군수" not in system
