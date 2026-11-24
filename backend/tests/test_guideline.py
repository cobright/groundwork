# -*- coding: utf-8 -*-
"""공모 가이드라인 — 모의데이터 '흐름 1'(AI 키 없이 규칙만으로)을 그대로 따라간다.

모의데이터/안내.txt 가 약속하는 결과: 항목 12개, 배점 5개 중 하나('지방비 확보')는
대응 목차가 없다는 경고, 마감일 후보 2026-11-20, 정정 공고 비교에서 마감일 1건·배점 2건.
"""
from conftest import mock_file


def _upload(client, pid, prefix):
    f = mock_file(prefix)
    r = client.post(f"/api/projects/{pid}/guidelines", params={"filename": f.name},
                    content=f.read_bytes())
    assert r.status_code == 201, r.text
    return r.json()


def _analyze(client, gid):
    r = client.post(f"/api/guidelines/{gid}/analyze", json={"use_ai": False})
    assert r.status_code == 200, r.text
    return r.json()


def test_공고문에서_목차_배점_마감일을_뽑는다(client, project):
    g = _upload(client, project, "01")
    assert g["range_guessed"] is True        # 범위는 추정일 뿐이라고 알린다
    a = _analyze(client, g["id"])

    assert a["fallback"] is True              # AI 없이 규칙만으로
    assert len(a["node_paths"]) == 12
    assert len(a["scoring"]) == 5
    missing = [m if isinstance(m, str) else m.get("label") or m.get("item")
               for m in a["scoring_match"]["missing_in_outline"]]
    assert any("지방비" in (m or "") for m in missing)
    assert "2026-11-20" in a["basic"]["마감일후보"]
    # 자료 후보에는 출처(원문 위치)가 붙는다 — 사람이 원문에서 확인할 수 있어야 한다
    assert a["needs"] and all("src_block" in n for n in a["needs"])


def test_분석은_제안만_한다_목차를_심지_않는다(client, project):
    g = _upload(client, project, "01")
    _analyze(client, g["id"])
    assert client.get(f"/api/projects/{project}/outline").json()["nodes"] == []


def test_정정_공고를_저장된_분석끼리_견준다(client, project):
    first = _upload(client, project, "01")
    _analyze(client, first["id"])
    fix = _upload(client, project, "06")
    _analyze(client, fix["id"])

    out = client.get(f"/api/guidelines/{fix['id']}/compare").json()
    assert out["available"] is True
    kinds = [c["kind"] for c in out["changes"]]
    assert kinds.count("마감일") == 1
    assert kinds.count("배점 변경") == 2
    assert out["summary"]["due"] == {"before": "2026-11-20", "after": "2026-11-27"}


def test_견줄_것이_없으면_없다고_말한다(client, project):
    g = _upload(client, project, "01")
    _analyze(client, g["id"])
    out = client.get(f"/api/guidelines/{g['id']}/compare").json()
    assert out["available"] is False and out["reason"]


def test_지자체가_아닌_공고도_같은_규칙으로_읽는다(client, project):
    """모의데이터/창업지원 — 창업기업의 지원사업 공고. 규칙이 지자체 용어에 묶여 있지 않은지 본다."""
    f = mock_file("01", sub="창업지원")
    g = client.post(f"/api/projects/{project}/guidelines", params={"filename": f.name},
                    content=f.read_bytes()).json()
    a = _analyze(client, g["id"])
    assert len(a["node_paths"]) == 12
    assert {p["label"] for p in a["scoring_match"]["pairs"]} == {"문제 인식", "실현 가능성", "성장 전략", "팀 구성"}
    assert [m["label"] for m in a["scoring_match"]["missing_in_outline"]] == ["자부담 확보"]
    assert "2027-03-19" in a["basic"]["마감일후보"]
