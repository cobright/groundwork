# -*- coding: utf-8 -*-
"""목차 파괴 방지·되돌리기와 업무 보관함 규칙."""


def _nodes(*titles):
    return {"nodes": [{"uid": f"n{i}", "parent_uid": None, "sort": i, "title": t}
                      for i, t in enumerate(titles)]}


def test_사라지는_항목이_있을_때만_스냅샷을_찍는다(client, project):
    base = f"/api/projects/{project}/outline"
    client.put(base, json=_nodes("가", "나", "다"))
    assert client.get(base + "/snapshots").json() == []       # 처음 심기 — 잃을 것이 없다

    client.put(base, json=_nodes("가(고침)", "나", "다"))      # 이름만 고침 — 잃을 것이 없다
    assert client.get(base + "/snapshots").json() == []

    client.put(base, json=_nodes("가"))                         # 둘이 사라진다
    snaps = client.get(base + "/snapshots").json()
    assert len(snaps) == 1


def test_되돌리면_사라진_항목과_카드가_돌아온다(client, project):
    base = f"/api/projects/{project}/outline"
    client.put(base, json=_nodes("가", "나"))
    client.put(f"/api/projects/{project}/cards/n1", json={"purpose": "나의 목적"})
    client.put(base, json=_nodes("가"))
    sid = client.get(base + "/snapshots").json()[0]["id"]

    r = client.post(f"{base}/snapshots/{sid}/restore")
    assert r.status_code == 200, r.text
    o = client.get(base).json()
    assert [n["title"] for n in o["nodes"]] == ["가", "나"]
    assert o["cards"]["n1"]["purpose"] == "나의 목적"     # 카드는 uid 에 묶여 따라온다


def test_진행중인_업무는_지울_수_없다_보관함에_든_것만(client, project):
    assert client.delete(f"/api/projects/{project}").status_code == 409

    client.post(f"/api/projects/{project}/archive", json={})
    assert all(p["id"] != project for p in client.get("/api/projects").json())   # 목록에서 빠진다

    assert client.delete(f"/api/projects/{project}").status_code in (200, 204)


def test_업무_저장은_보낸_필드만_고친다(client, project):
    client.put(f"/api/projects/{project}", json={"purpose": "목적"})
    p = client.get(f"/api/projects/{project}").json()
    p = p.get("project", p)
    assert p["name"] == "시험 업무" and p["purpose"] == "목적"


def test_없는_API_경로는_뜻있는_404(client):
    r = client.post("/api/없는-경로")
    assert r.status_code == 404
