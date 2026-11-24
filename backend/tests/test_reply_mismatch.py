# -*- coding: utf-8 -*-
"""요청과 다른 회신 · 빈 주장 · 지워진 회신 — 2026-11-24 실제 업무(#6)를 끝까지 써 보다 드러난 것.

#6 에서 '읍·면별 인구지표'를 요청했는데 '지방소멸대응기금 건의안' 파일이 회신으로 등록됐다.
AI 분석은 "요청한 ○○은(는) 이 자료에 없습니다"로 정확히 알렸지만 그대로 확정됐고,
최종본 부록에 근거자료가 요청 이름(‘읍·면별 … ✔’)으로 찍혔다. 주장은 '새 주장' 그대로였다.
"""
import json

import pytest

from app.skills import resource_analysis
from app.skills.resource_analysis import asked_missing

NEED = "읍·면별 최근 5년간 인구증감률, 고령화비율"
WRONG = json.dumps({
    "summary": "요청한 인구지표가 아니라 지방소멸대응기금 분할신청제 건의안입니다.",
    "key_points": ["기본배분 72억 원"], "usable_for": [],
    "cautions": ["요청한 읍·면별 최근 5년간 인구증감률은 이 자료에 없습니다 — 추가 요청 필요",
                 "요청한 읍·면별 고령화비율은 이 자료에 없습니다 — 추가 요청 필요",
                 "기준일이 기재되어 있지 않습니다."]}, ensure_ascii=False)


@pytest.fixture
def wrong_reply(client, project, fake_ai):
    fp = fake_ai(WRONG, resource_analysis)
    client.put(f"/api/projects/{project}/outline", json={"nodes": [{"uid": "n1", "sort": 0, "title": "인구 현황"}]})
    q = client.post(f"/api/projects/{project}/requests", json={"need": NEED, "status": "요청함"}).json()
    r = client.post(f"/api/projects/{project}/requests/{q['id']}/received-file",
                    params={"filename": "건의안.html"},
                    content="<table><tr><td>지방소멸대응기금 기본배분 72억 원</td></tr></table>".encode())
    assert r.status_code == 201, r.text
    rid = r.json()["resource_id"]
    client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    assert NEED in fp.calls[0][1].content                 # 무엇을 요청했는지가 분석에 넘어간다
    return {"c": client, "pid": project, "rid": rid, "qid": q["id"]}


def _res(s):
    return next(x for x in s["c"].get(f"/api/projects/{s['pid']}/resources").json() if x["id"] == s["rid"])


def test_분석이_요청과_다르다고_하면_화면에_따로_알린다(wrong_reply):
    r = _res(wrong_reply)
    assert len(r["analysis"]["asked_missing"]) == 2           # '기준일' 같은 다른 주의는 섞지 않는다
    assert r["reply_of"] == {"id": wrong_reply["qid"], "need": NEED, "status": "회신옴"}


def test_요청과_다른_회신은_확인_없이_확정되지_않는다(wrong_reply):
    s = wrong_reply
    r = s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/confirm", json={})
    assert r.status_code == 409 and "요청한 것 2가지" in r.json()["detail"]
    assert _res(s)["analysis"]["state"] == "분석 완료"
    # 사람이 보고도 확정하겠다면 막지 않는다(원칙 1 — 판단은 사람이)
    r = s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/confirm", json={"force": True})
    assert r.status_code == 200 and r.json()["state"] == "사용자 확정"


def test_요청과_맞는_회신은_묻지_않고_확정된다(client, project, fake_ai):
    fake_ai(json.dumps({"summary": "인구", "key_points": ["요청한 인구증감률: -1.2%"], "usable_for": [],
                        "cautions": []}, ensure_ascii=False), resource_analysis)
    rid = client.post(f"/api/projects/{project}/resources", json={"name": "인구", "text": "-1.2%"}).json()["id"]
    client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    assert client.post(f"/api/projects/{project}/resources/{rid}/confirm").status_code == 200


def test_재요청으로_되돌리면_요청은_다시_요청함_자료는_이름표를_단다(wrong_reply):
    s = wrong_reply
    r = s["c"].post(f"/api/projects/{s['pid']}/requests/{s['qid']}/reopen", json={"reason": "다른 파일이 옴"})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["status"] == "요청함" and q["received_resource_id"] is None and not q["received_lost"]
    assert "회신이 요청과 달라 재요청 — 다른 파일이 옴" in q["received_note"]
    res = _res(s)
    assert res["name"].startswith("[요청과 다름] ") and res["reply_of"] is None   # 자료는 지우지 않는다
    # 다시 올바른 파일을 받을 수 있다
    r = s["c"].post(f"/api/projects/{s['pid']}/requests/{s['qid']}/received-file",
                    params={"filename": "인구.html"}, content="<table><tr><td>-1.2%</td></tr></table>".encode())
    assert r.status_code == 201
    # 두 번 되돌려도 이름표가 겹치지 않는다
    s["c"].post(f"/api/projects/{s['pid']}/requests/{s['qid']}/reopen", json={})
    assert not _res(s)["name"].startswith("[요청과 다름] [요청과 다름]")


def _labels(s):
    return {i["label"]: i for i in s["c"].get(f"/api/projects/{s['pid']}/final-check").json()["items"]}


def test_최종본_점검이_요청과_다른_회신과_빈_주장을_짚는다(wrong_reply):
    s = wrong_reply
    s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/confirm", json={"force": True})
    s["c"].post(f"/api/projects/{s['pid']}/evidence", json={"claim": "새 주장", "resource_id": s["rid"], "node_uid": "n1"})
    s["c"].post(f"/api/projects/{s['pid']}/evidence", json={"claim": "", "resource_id": None})
    got = _labels(s)
    assert "E-001" in got["요청과 다른 회신을 근거로 씀"]["detail"][0]
    assert got["요청과 다른 회신을 근거로 씀"]["level"] == "중요"
    assert [d[:5] for d in got["주장이 비어 있는 근거"]["detail"]] == ["E-001", "E-002"]


def test_회신_자료를_지우면_점검이_알린다(wrong_reply):
    s = wrong_reply
    s["c"].delete(f"/api/projects/{s['pid']}/resources/{s['rid']}")
    item = _labels(s)["회신 자료가 지워진 자료요청"]
    assert item["level"] == "참고" and NEED[:20] in item["detail"][0]


def test_요청_대조_문구만_골라낸다():
    assert asked_missing(["요청한 A는 이 자료에 없습니다 — 추가 요청 필요", "기준일 없음",
                          "A는 이 자료에 없습니다", None]) == ["요청한 A는 이 자료에 없습니다 — 추가 요청 필요"]
