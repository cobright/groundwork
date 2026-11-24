# -*- coding: utf-8 -*-
"""원칙 2 — 모든 것은 근거로 통제된다.

자료 → AI 분석(제안) → 사람의 확정 → 근거. 자료가 바뀌면 그 자료를 쓴 근거에 신호가 뜨고,
그 신호는 사람이 '확인함'을 눌러야만 내려간다.
"""
import json

from app.skills import resource_analysis

ANSWER = json.dumps({
    "summary": "읍·면별 노인 인구 현황",
    "key_points": ["65세 이상 15,600명"],
    "usable_for": ["사업 필요성"],
    "cautions": [],
}, ensure_ascii=False)


def _resource(client, pid, text="65세 이상 인구 15,600명"):
    r = client.post(f"/api/projects/{pid}/resources",
                    json={"name": "노인인구 현황", "kind": "통계", "text": text})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_분석은_제안이고_확정은_사람이_한다(client, project, fake_ai):
    fp = fake_ai(ANSWER, resource_analysis)
    rid = _resource(client, project)

    # 분석 전에는 확정할 수 없다
    assert client.post(f"/api/projects/{project}/resources/{rid}/confirm").status_code == 400

    a = client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={}).json()
    assert a["state"] == "분석 완료"          # '확정'이 아니다
    assert a["model"] == "fake-model"         # 결과에 찍힌 모델 이름이 실제로 부른 것과 같다
    assert fp.calls, "가짜 AI 가 불리지 않았다"

    a = client.post(f"/api/projects/{project}/resources/{rid}/confirm").json()
    assert a["state"] == "사용자 확정"


def test_AI_실패는_502로_그대로_알린다(client, project, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("키가 없습니다")
    monkeypatch.setattr(resource_analysis, "get_provider", boom)
    rid = _resource(client, project)
    r = client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    assert r.status_code == 502
    assert "키가 없습니다" in r.json()["detail"]


def test_자료가_바뀌면_근거에_신호가_뜨고_확인해야만_내려간다(client, project, fake_ai):
    fake_ai(ANSWER, resource_analysis)
    rid = _resource(client, project)
    client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    client.post(f"/api/projects/{project}/resources/{rid}/confirm")
    ev = client.post(f"/api/projects/{project}/evidence",
                     json={"claim": "노인 인구가 많다", "resource_id": rid}).json()
    assert ev["source_changed"] == 0

    # 자료 본문을 고친다 → 확정이 풀리고 근거에 신호
    body = {"name": "노인인구 현황", "kind": "통계", "text": "65세 이상 인구 15,700명"}
    r = client.put(f"/api/projects/{project}/resources/{rid}", json=body).json()
    assert r["analysis"]["state"] == "재분석 필요"
    ev = client.get(f"/api/projects/{project}/evidence").json()[0]
    assert ev["source_changed"] == 1

    # 근거 항목을 고쳐도 신호는 꺼지지 않는다
    client.put(f"/api/projects/{project}/evidence/{ev['id']}",
               json={"claim": "노인 인구가 많다(수정)", "resource_id": rid})
    assert client.get(f"/api/projects/{project}/evidence").json()[0]["source_changed"] == 1

    # '확인함'으로만 내려간다
    ev = client.post(f"/api/projects/{project}/evidence/{ev['id']}/acknowledge").json()
    assert ev["source_changed"] == 0


def test_담당자_메모는_확정을_풀지_않는다(client, project, fake_ai):
    fake_ai(ANSWER, resource_analysis)
    rid = _resource(client, project)
    client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    client.post(f"/api/projects/{project}/resources/{rid}/confirm")
    client.post(f"/api/projects/{project}/evidence", json={"claim": "c", "resource_id": rid})

    body = {"name": "노인인구 현황", "kind": "통계", "text": "65세 이상 인구 15,600명",
            "note": "이 표는 주민등록 기준이라 외국인이 빠져 있다"}
    r = client.put(f"/api/projects/{project}/resources/{rid}", json=body).json()
    assert r["analysis"]["state"] == "사용자 확정"
    assert client.get(f"/api/projects/{project}/evidence").json()[0]["source_changed"] == 0


def test_업무에_없는_자료는_근거로_이을_수_없다(client, project):
    other = client.post("/api/projects", json={"name": "다른 업무"}).json()["id"]
    rid = _resource(client, other)
    r = client.post(f"/api/projects/{project}/evidence", json={"claim": "c", "resource_id": rid})
    assert r.status_code == 400
