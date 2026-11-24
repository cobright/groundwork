# -*- coding: utf-8 -*-
"""근거 점검기(services/evidence_check.py) — 원칙 2 를 지시문이 아니라 규칙으로 지키는지.

모의데이터 02(가온군 노인인구 xlsx)를 근거 원문으로 쓴다: 2026년 65세 이상 15,600명, 고령화율 37.1%,
북계면 고령화율 51(%), 독거노인 4,530명.
"""
import json

import pytest

from app.skills import draft_writing, resource_analysis
from app.services.evidence_check import check_text, numbers_in, split_sentences
from conftest import mock_file

# AI 요약에 일부러 원문에 없는 숫자(99,999)를 넣는다 — 점검기가 요약을 원문으로 믿지 않는지 보려고
ANALYSIS = json.dumps({"summary": "65세 이상 99,999명", "key_points": [], "usable_for": [], "cautions": []},
                      ensure_ascii=False)


@pytest.fixture
def setup(client, project, fake_ai):
    """목차 하나 + 확정한 엑셀 자료 + 그 자료를 쓴 근거 E-001."""
    fake_ai(ANALYSIS, resource_analysis)
    client.put(f"/api/projects/{project}/outline",
               json={"nodes": [{"uid": "n1", "sort": 0, "title": "노인 인구 현황"}]})
    f = mock_file("02")
    rid = client.post(f"/api/projects/{project}/resources/upload", params={"filename": f.name, "name": "노인인구"},
                      content=f.read_bytes()).json()["id"]
    client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    client.post(f"/api/projects/{project}/resources/{rid}/confirm")
    ev = client.post(f"/api/projects/{project}/evidence",
                     json={"claim": "노인 인구가 늘었다", "resource_id": rid, "node_uid": "n1"}).json()
    assert ev["ev_no"] == "E-001"
    return {"pid": project, "rid": rid, "client": client}


def _save(s, body):
    r = s["client"].put(f"/api/projects/{s['pid']}/nodes/n1/draft", json={"body": body})
    assert r.status_code == 200, r.text
    return r.json()["check"]


def _kinds(found):
    return [f["kind"] for f in found]


def test_원문과_맞는_본문은_의견이_없다(setup):
    body = ("2026년 65세 이상 인구는 15,600명이다(근거: E-001).\n"
            "고령화율은 37.1%이며 북계면이 51%로 가장 높다. (근거: E-001)")
    assert _save(setup, body) == []


def test_원문에_없는_숫자를_짚는다(setup):
    found = _save(setup, "65세 이상 인구는 15,700명이다(근거: E-001).")
    assert _kinds(found) == ["원문에 없는 숫자"]
    assert "15,700" in found[0]["text"] and found[0]["ev"] == "E-001"


def test_AI_요약은_원문으로_치지_않는다(setup):
    # 99,999 는 AI 요약에만 있고 자료 원문에는 없다
    assert _kinds(_save(setup, "65세 이상 인구는 99,999명이다(근거: E-001).")) == ["원문에 없는 숫자"]


def test_없는_근거_번호를_짚는다(setup):
    found = _save(setup, "독거노인은 4,530명이다(근거: E-001, E-009).")
    assert _kinds(found) == ["없는 근거 번호"] and found[0]["level"] == "중대"


def test_근거_번호_없는_수치_문장을_짚고_스스로_표시한_문장은_두다(setup):
    found = _save(setup, "경로당 132개소 중 30%가 낡았다.\n[확인 필요: 노후 비율] 30%가 낡았다.\n2027년까지 추진한다.")
    assert _kinds(found) == ["근거 없는 수치 문장"]       # 연도만 있는 문장은 짚지 않는다


def test_미확정_근거와_바뀐_원본을_짚는다(setup):
    s = setup
    c, pid, rid = s["client"], s["pid"], s["rid"]
    cur = next(x for x in c.get(f"/api/projects/{pid}/resources").json() if x["id"] == rid)
    body = {k: cur[k] for k in ("name", "kind", "source_org", "base_date", "trust", "note")}
    c.put(f"/api/projects/{pid}/resources/{rid}", json={**body, "text": cur["text"] + "\n정정"})   # 확정 풀림 + 신호
    found = _save(s, "65세 이상 인구는 15,600명이다(근거: E-001).")
    assert set(_kinds(found)) == {"미확정 근거 인용", "원본이 바뀐 근거 인용"}


def test_초고에는_미확정_근거를_넘기지_않는다(setup, fake_ai):
    c, pid = setup["client"], setup["pid"]
    other = c.post(f"/api/projects/{pid}/resources", json={"name": "확정 안 한 자료", "text": "1,234명"}).json()["id"]
    c.post(f"/api/projects/{pid}/evidence", json={"claim": "미확정 주장 문장", "resource_id": other, "node_uid": "n1"})
    fp = fake_ai("인구는 15,600명이다(근거: E-001). 다른 값은 1,234명이다(근거: E-002).", draft_writing)

    r = c.post(f"/api/projects/{pid}/nodes/n1/draft/generate", json={"strictness": "엄격"}).json()
    prompt = fp.calls[0][1].content
    assert "노인 인구가 늘었다" in prompt and "미확정 주장 문장" not in prompt
    assert [x["ev_no"] for x in r["excluded"]] == ["E-002"]
    # AI 가 미확정 근거를 지어내 인용해도 점검기가 짚는다
    assert "미확정 근거 인용" in _kinds(r["check"])

    # '자료목록' 모드는 무엇이 더 필요한지 말하는 일이라 미확정 근거도 보여 준다
    fp2 = fake_ai("- 자료 목록", draft_writing)
    c.post(f"/api/projects/{pid}/nodes/n1/draft/generate", json={"strictness": "자료목록"})
    assert "미확정 주장 문장" in fp2.calls[0][1].content


def test_초고_화면은_제안과_본문을_각각_점검해_준다(setup):
    _save(setup, "인구는 15,700명이다(근거: E-001).")
    d = setup["client"].get(f"/api/projects/{setup['pid']}/nodes/n1/draft").json()
    assert _kinds(d["check"]["body"]) == ["원문에 없는 숫자"] and d["check"]["suggestion"] == []


def test_최종본_점검에_근거_점검이_들어간다(setup):
    _save(setup, "인구는 15,700명이다(근거: E-009).")
    chk = setup["client"].get(f"/api/projects/{setup['pid']}/final-check").json()
    labels = [i["label"] for i in chk["items"]]
    assert "근거 점검: 없는 근거 번호" in labels
    assert chk["ok"] is False
    detail = next(i for i in chk["items"] if i["label"] == "근거 점검: 없는 근거 번호")["detail"][0]
    assert detail.startswith("1 노인 인구 현황")


# ── 규칙 단위 ──
def test_따로_떨어진_근거_꼬리는_앞_문장에_붙는다():
    assert split_sentences("늘었다. (근거: E-001)\n다음 문장.") == ["늘었다. (근거: E-001)", "다음 문장."]


def test_숫자_정규화와_양_판별():
    got = {(n, q) for _, n, q in numbers_in("15,600명, 45.90%, 2026년, E-012, 3,000만원")}
    assert got == {("15600", True), ("45.9", True), ("2026", False), ("3000", True)}


def test_근거가_없으면_빈_본문도_조용하다():
    assert check_text("", {}) == []


def test_줄_끝_근거_번호는_그_줄의_앞_문장도_받친다(setup):
    # 2026-11-24 실제 AI 출력에서 첫 문장을 '근거 없는 수치'로 잘못 짚었던 꼴
    body = ("- 총인구는 2024년 43,610명에서 2026년 42,000명으로 감소하였다. "
            "반면 65세 이상 인구는 같은 기간 14,840명에서 15,600명으로 증가하였다. (근거: E-001)")
    assert _save(setup, body) == []


def test_물려받은_문장도_숫자는_대조한다(setup):
    found = _save(setup, "인구는 99,999명이다. 고령화가 심하다(근거: E-001).")
    assert _kinds(found) == ["원문에 없는 숫자"] and "99,999" in found[0]["text"]


def test_앞_문장의_번호는_뒤_문장을_받치지_않는다(setup):
    found = _save(setup, "인구는 15,600명이다(근거: E-001). 경로당은 132개소다.")
    assert _kinds(found) == ["근거 없는 수치 문장"]


def test_번호_문제는_물려받은_문장에서_되풀이하지_않는다(setup):
    found = _save(setup, "인구는 15,600명이다. 고령화율은 37.1%다(근거: E-009).")
    assert _kinds(found) == ["없는 근거 번호"]        # 앞 문장에서 한 번 더 짚지 않는다


# ── 초고의 마크다운 정리(draft_writing.tidy_markup) ──
from app.skills.draft_writing import tidy_markup   # noqa: E402


def test_목차_제목을_되풀이한_마크다운_줄은_빼고_나머지는_표시만_뗀다():
    text, notes = tidy_markup("### 1. 노인 인구 현황\n\n- 인구는 **15,600명**이다.\n### 가. 세부", "노인 인구 현황", "2.1")
    assert text == "- 인구는 15,600명이다.\n가. 세부"
    assert len(notes) == 3


def test_마크다운이_없으면_그대로_둔다():
    assert tidy_markup("- 본문 #해시 아님\n○ 둘째", "x") == ("- 본문 #해시 아님\n○ 둘째", [])


def test_초고_생성은_정리한_것을_알려준다(setup, fake_ai):
    fake_ai("## 노인 인구 현황\n인구는 15,600명이다(근거: E-001).", draft_writing)
    r = setup["client"].post(f"/api/projects/{setup['pid']}/nodes/n1/draft/generate", json={}).json()
    assert r["ai_suggestion"] == "인구는 15,600명이다(근거: E-001)."
    assert r["tidied"] and r["check"] == []


def test_날짜를_옮겨_써도_앞자리_0_때문에_짚지_않는다():
    """2026-11-24 실제 AI 품질 시험(C10): 원문 '2026-10-05' 를 초고가 '10월 5일'로 옮겼는데
    '5' 를 '05' 와 다른 숫자로 보아 '원문에 없는 숫자'로 짚었다(헛경보)."""
    from app.services.evidence_check import norm_num
    assert [norm_num(x) for x in ("05", "0.5", "007", "0", "10", "1,200")] == ["5", "0.5", "7", "0", "10", "1200"]
    index = {"E-004": {"mark": "확정", "source_changed": False, "quote_state": "일치", "plain": "", "claim": "",
                       "nums": {n for _, n, _ in numbers_in("조사 기간 │ 2026-10-05 ~ 2026-10-16 │ 응답자 │ 120명(온라인)")}}}
    sent = "고객 설문은 2026년 10월 5일부터 10월 16일까지 온라인 응답자 120명을 대상으로 제시되었다. (근거: E-004)"
    assert check_text(sent, index) == []
    assert check_text(sent.replace("120명", "150명"), index)[0]["kind"] == "원문에 없는 숫자"   # 진짜로 다른 수는 여전히 짚는다
