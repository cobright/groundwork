# -*- coding: utf-8 -*-
"""배점 대비 충실도 지도 — 가이드라인이 카드에 실은 배점 문장을 되읽어, 배점·분량·확정 근거를 한 표에.

모의 공고(01_)의 규칙 분석은 배점 다섯 중 넷을 목차에 짝짓는다:
사업 필요성 25 · 사업 내용의 구체성 30 · 추진 체계 및 사후 관리 20 · 기대 효과 15 (지방비 확보 10 은 대응 목차 없음).
"""
from conftest import mock_file

from app.services.guideline import parse_score_note, score_note


def test_배점_문장은_만든_그대로_되읽힌다():
    hits = [{"label": "사업 필요성", "points_text": "25", "confidence": 0.8},
            {"label": "기대 효과", "points_text": "15점", "confidence": 0.9}]
    assert parse_score_note("작성 목적…\n" + score_note(hits)) == [
        {"label": "사업 필요성", "points": 25.0, "low": False}, {"label": "기대 효과", "points": 15.0, "low": False}]
    low = parse_score_note(score_note([{"label": "추진 체계", "points_text": "", "confidence": 0.3}]))
    assert low == [{"label": "추진 체계", "points": None, "low": True}]
    assert parse_score_note("배점 문장이 없는 카드") == []


def _plant(client, pid):
    """가이드라인 분석의 목차 틀을 화면(buildFromTemplate)처럼 심는다 — uid 를 매기고 목차·카드를 저장."""
    f = mock_file("01_")
    g = client.post(f"/api/projects/{pid}/guidelines", params={"filename": f.name}, content=f.read_bytes()).json()
    tree = client.post(f"/api/guidelines/{g['id']}/analyze", json={"use_ai": False}).json()["tree"]
    nodes, cards, uid_of = [], {}, {}

    def walk(ns, parent):
        for i, n in enumerate(ns):
            uid = f"u{len(nodes)}"
            nodes.append({"uid": uid, "parent_uid": parent, "sort": i, "title": n["title"]})
            cards[uid] = n.get("card") or {}
            uid_of[n["title"]] = uid
            walk(n.get("children", []), uid)
    walk(tree, None)
    client.put(f"/api/projects/{pid}/outline", json={"nodes": nodes})
    for uid, card in cards.items():
        client.put(f"/api/projects/{pid}/cards/{uid}", json={**card, "length": card.get("length") or "1쪽"})
    return uid_of


def test_배점_분량_근거를_한_표에_놓고_빈_곳을_짚는다(client, project):
    uid = _plant(client, project)
    # 필요성(25점): 본문 + 확정 근거 / 추진 내용(30점): 본문만 길게, 근거 없음 / 나머지는 비어 있음
    client.put(f"/api/projects/{project}/nodes/{uid['사업 배경 및 필요성']}/draft", json={"body": "가" * 200})
    client.put(f"/api/projects/{project}/nodes/{uid['추진 내용']}/draft", json={"body": "나" * 2000})
    rid = client.post(f"/api/projects/{project}/statements", json={"text": "경로당 42개소"}).json()["resource"]["id"]
    client.post(f"/api/projects/{project}/statements/{rid}/adopt",
                json={"claims": [{"claim": "경로당 42개소"}], "node_uid": uid["사업 배경 및 필요성"]})

    m = client.get(f"/api/projects/{project}/score-map").json()
    rows = {r["label"]: r for r in m["items"]}
    assert [r["points"] for r in m["items"]] == [30, 25, 20, 15]          # 배점 큰 것부터
    assert m["total_points"] == 90
    need, body = rows["사업 필요성"], rows["사업 내용의 구체성"]
    assert (need["chars"], need["evidence"]) == (200, 1) and "확정 근거 0건" not in need["flags"]
    assert body["evidence"] == 0 and "확정 근거 0건" in body["flags"]
    # 필요성: 배점 몫 28% · 분량 몫 9% → 절반도 안 된다
    assert any(f.startswith("분량 몫") for f in need["flags"])
    assert "본문 없음" in rows["기대 효과"]["flags"]

    items = client.get(f"/api/projects/{project}/final-check").json()["items"]
    no_ev = next(i for i in items if i["label"] == "심사배점 항목에 확정 근거가 없음")
    assert any(d.startswith("‘사업 내용의 구체성’ 30점") for d in no_ev["detail"])
    assert not any("사업 필요성" in d for d in no_ev["detail"])
    thin = next(i for i in items if i["label"] == "배점에 비해 분량이 얇은 항목")
    assert thin["level"] == "참고"


def test_배점이_걸린_목차_아래_목차의_본문과_근거도_센다(client, project):
    client.put(f"/api/projects/{project}/outline", json={"nodes": [
        {"uid": "p", "sort": 0, "title": "추진 내용"}, {"uid": "c1", "parent_uid": "p", "sort": 0, "title": "세부 1"}]})
    client.put(f"/api/projects/{project}/cards/p", json={"purpose": score_note(
        [{"label": "사업 내용의 구체성", "points_text": "30", "confidence": 0.9}])})
    client.put(f"/api/projects/{project}/nodes/c1/draft", json={"body": "세부 내용입니다"})
    rid = client.post(f"/api/projects/{project}/statements", json={"text": "x"}).json()["resource"]["id"]
    client.post(f"/api/projects/{project}/statements/{rid}/adopt", json={"claims": [{"claim": "x"}], "node_uid": "c1"})
    r = client.get(f"/api/projects/{project}/score-map").json()["items"][0]
    assert (r["chars"], r["evidence"], r["nodes"]) == (len("세부내용입니다"), 1, ["1 추진 내용"])


def test_배점이_없으면_표가_비고_점검도_조용하다(client, project):
    client.put(f"/api/projects/{project}/outline", json={"nodes": [{"uid": "a", "sort": 0, "title": "현황"}]})
    m = client.get(f"/api/projects/{project}/score-map").json()
    assert m["items"] == [] and m["unscored"] == [{"node": "1 현황", "chars": 0}]
    labels = [i["label"] for i in client.get(f"/api/projects/{project}/final-check").json()["items"]]
    assert "심사배점 항목에 확정 근거가 없음" not in labels
