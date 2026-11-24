# -*- coding: utf-8 -*-
"""최종본 .docx 내보내기 — 사용자가 마지막에 손에 쥐는 것.

API 로 실제 파일을 받아 python-docx 로 다시 열어 본다: 제목·목차 번호·본문(사람이 반영한 것만)·
근거 부록(본문의 E-번호를 찾아갈 수 있게)·보고전 서식.
"""
import io

import pytest
from docx import Document


def _outline(client, pid, nodes):
    r = client.put(f"/api/projects/{pid}/outline", json={"nodes": nodes})
    assert r.status_code == 200, r.text


def _body(client, pid, uid, text):
    assert client.put(f"/api/projects/{pid}/nodes/{uid}/draft", json={"body": text}).status_code == 200


def _export(client, pid, **params):
    r = client.get(f"/api/projects/{pid}/export.docx", params=params)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    return r, Document(io.BytesIO(r.content))


def _texts(doc):
    return [p.text for p in doc.paragraphs if p.text.strip()]


@pytest.fixture
def plan(client, project):
    _outline(client, project, [
        {"uid": "a", "sort": 0, "title": "추진 배경"},
        {"uid": "a1", "parent_uid": "a", "sort": 1, "title": "지역 현황"},
        {"uid": "b", "sort": 2, "title": "기대 효과"},
    ])
    rid = client.post(f"/api/projects/{project}/resources", json={"name": "인구 통계", "text": "15,600명"}).json()["id"]
    client.post(f"/api/projects/{project}/evidence",
                json={"claim": "노인 인구가 늘었다", "resource_id": rid, "locator": "표 1", "node_uid": "a1"})
    _body(client, project, "a1", "65세 이상 인구는 15,600명이다(근거: E-001).\n\n둘째 문단.")
    return project


def test_계획서는_제목_번호_본문을_목차_순서대로_담는다(client, plan):
    r, doc = _export(client, plan)
    t = _texts(doc)
    assert t[0] == "시험 업무" and t[1] == "공모사업 계획서"
    heads = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert heads[:3] == ["1 추진 배경", "1.1 지역 현황", "2 기대 효과"]
    assert "65세 이상 인구는 15,600명이다(근거: E-001)." in t
    assert "둘째 문단." in t                       # 빈 줄은 문단을 만들지 않는다
    assert t.count("(본문 없음)") == 2               # 본문 없는 목차는 숨기지 않고 드러낸다
    assert "filename*=UTF-8''" in r.headers["content-disposition"]


def test_AI_제안은_최종본에_들어가지_않는다(client, plan):
    # 반영하지 않은 AI 제안이 있어도 최종본은 사람이 반영한 본문만 담는다(원칙 1)
    from app import db
    with db.connect() as c:
        c.execute("UPDATE drafts SET ai_suggestion='반영 안 한 AI 문장' WHERE node_uid='a1'")
    _, doc = _export(client, plan)
    assert not any("반영 안 한 AI 문장" in p for p in _texts(doc))


def test_근거_부록은_본문의_번호를_찾아가게_한다(client, plan):
    _, doc = _export(client, plan)
    assert "[부록] 근거표" in _texts(doc)
    rows = [[c.text for c in row.cells] for row in doc.tables[0].rows]
    assert rows[0] == ["번호", "주장·판단", "근거자료", "위치·원문 인용", "상태"]
    assert rows[1][:4] == ["E-001", "노인 인구가 늘었다", "인구 통계", "표 1"]   # 미확정이라 ✔ 없음


def test_확정한_근거에는_표시가_붙는다(client, plan):
    from app import db
    with db.connect() as c:
        rid = c.execute("SELECT id FROM resources").fetchone()["id"]
        c.execute("INSERT INTO resource_analysis(resource_id,summary,key_points,usable_for,cautions,state,model,analyzed_at)"
                  " VALUES(?,?,?,?,?,?,?,?)", (rid, "", "[]", "[]", "[]", "사용자 확정", "", ""))
    _, doc = _export(client, plan)
    assert doc.tables[0].rows[1].cells[2].text == "인구 통계 ✔"


def test_부록을_빼고_내보낼_수_있다(client, plan):
    _, doc = _export(client, plan, include_evidence=False)
    assert doc.tables == [] and "[부록] 근거표" not in _texts(doc)


def test_보고전은_번호_없이_줄머리로_한_쪽에(client):
    pid = client.post("/api/projects", json={"name": "폐교 현황 보고", "doc_type": "보고전 · 상황 보고"}).json()["id"]
    r = client.put("/api/settings", json={"author_name": "홍길동", "author_dept": "기획팀"})
    assert r.status_code == 200, r.text
    _outline(client, pid, [
        {"uid": "x", "sort": 0, "title": "본문"},
        {"uid": "x1", "parent_uid": "x", "sort": 1, "title": "실태"},
        {"uid": "y", "sort": 2, "title": "조치의견"},
    ])
    _body(client, pid, "x1", "○ 지붕 일부 붕괴\n- 인근 10가구 민원")
    _, doc = _export(client, pid)
    t = _texts(doc)
    assert t[0].startswith("기획팀 · 홍길동 · ")        # 머리글: 부서 · 작성자 · 날짜
    assert t[1] == "폐교 현황 보고"
    assert "□ 본문" in t and "○ 실태" in t and "□ 조치의견" in t
    assert not any(p.style.name.startswith("Heading") for p in doc.paragraphs if p.text.strip())
    assert "○ 지붕 일부 붕괴" in t and "- 인근 10가구 민원" in t
    assert t.count("(본문 없음)") == 1                # 하위를 거느린 '본문'에는 찍지 않는다
    assert doc.sections[0].top_margin.mm == pytest.approx(15, abs=0.1)


def test_없는_업무는_404(client):
    assert client.get("/api/projects/999/export.docx").status_code == 404
