# -*- coding: utf-8 -*-
"""항목 간 정합성 점검(규칙) — 같은 지표가 목차마다 다른 값으로 나오는 곳.

1장에 '65세 이상 인구 15,600명', 3장에 '15,700명'으로 써도 목차 하나씩 보는 점검은 못 잡았다.
여기서는 짚어야 할 것을 짚는지와 함께, **짚지 말아야 할 것을 짚지 않는지**를 더 많이 본다 —
헛경보가 많으면 사람이 점검 전체를 안 보게 된다.
"""
from app.services.consistency import check_sections, facts_in


def _s(*bodies):
    return [{"number": str(i + 1), "title": f"항목{i + 1}", "body": b} for i, b in enumerate(bodies)]


def _texts(*bodies):
    return [f["text"] for f in check_sections(_s(*bodies))]


def test_같은_지표가_다른_값이면_짚는다():
    got = check_sections(_s("2026년 65세 이상 인구는 15,600명이다.", "2026년 65세 이상 인구 15,700명을 대상으로 한다."))
    assert len(got) == 1
    assert got[0]["indicator"] == "65세이상 인구(2026년)" and set(got[0]["values"]) == {"15600", "15700"}
    assert "1 항목1" in got[0]["text"] and "2 항목2" in got[0]["text"]


def test_같은_값이면_조용하다():
    assert _texts("2026년 고령화율은 37.1%다.", "고령화율이 2026년 37.1%에 이르러") == []


def test_지명이_다르면_다른_지표다():
    # 가장 흔한 헛경보 — 읍·면 값과 군 전체 값
    assert _texts("2026년 가온읍의 총인구는 18,420명이다.", "2026년 북계면의 총인구는 2,960명이다.") == []


def test_앞_마디의_지명을_뒤_마디가_잇는다():
    """'가온읍의 총인구는 …, 65세 이상 인구는 …' 의 뒤 마디를 군 전체 65세 이상 인구와 섞지 않는다."""
    facts = facts_in("2026년 가온읍의 총인구는 18,420명, 65세 이상 인구는 4,790명이다.")
    assert [f["subject"] for f in facts] == ["가온읍 총인구", "가온읍 65세이상 인구"]
    assert _texts("2026년 가온읍의 총인구는 18,420명, 65세 이상 인구는 4,790명이다.",
                  "2026년 65세 이상 인구는 15,600명이다.") == []


def test_나이_기준이_다르면_다른_지표다():
    assert _texts("2026년 65세 이상 인구는 15,600명이다.", "2026년 75세 이상 인구는 7,000명이다.") == []


def test_연도가_다르면_다른_지표다():
    facts = facts_in("가온군의 총인구는 2024년 43,610명, 2025년 42,780명, 2026년 42,000명이다.")
    assert [(f["year"], f["value"]) for f in facts] == [("2024", "43610"), ("2025", "42780"), ("2026", "42000")]
    assert _texts("가온군의 총인구는 2024년 43,610명, 2026년 42,000명이다.") == []


def test_어느_해인지_모르는_목록은_건너뛴다():
    """'각각' 목록은 값과 해를 짝지을 수 없다 — 틀리게 잇느니 안 본다."""
    assert facts_in("65세 이상 인구는 같은 기간 각각 14,840명, 15,220명, 15,600명이다.") == []
    assert facts_in("2024년과 2026년 고령화율은 35%, 37.1%다.") == []


def test_연도와_근거_번호는_값이_아니다():
    facts = facts_in("2026년 독거노인은 4,530명이다. (근거: E-001)")
    assert [(f["subject"], f["value"]) for f in facts] == [("독거노인", "4530")]


def test_최종본_점검에_나온다(client, project):
    client.put(f"/api/projects/{project}/outline", json={"nodes": [
        {"uid": "a", "sort": 0, "title": "현황"}, {"uid": "b", "sort": 1, "title": "기대 효과"}]})
    client.put(f"/api/projects/{project}/nodes/a/draft", json={"body": "2026년 65세 이상 인구는 15,600명이다."})
    client.put(f"/api/projects/{project}/nodes/b/draft", json={"body": "2026년 65세 이상 인구 15,700명이 혜택을 본다."})
    items = client.get(f"/api/projects/{project}/final-check").json()["items"]
    it = next(i for i in items if i["label"] == "같은 지표가 목차마다 다른 값으로 나옴")
    assert it["level"] == "중요" and "15,600명 — 1 현황" in it["detail"][0] and "15,700명 — 2 기대 효과" in it["detail"][0]
