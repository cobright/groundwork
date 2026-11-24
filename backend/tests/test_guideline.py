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


def test_서식_표_자료요구에_표_이름을_붙이고_서명란은_뺀다():
    """실물 #7(2026-11-25): 서식 표의 머리글만 자료요청이 되어('읍·면 · 명칭 · 이용현황 · 소재지 · 비 고')
    부서가 무엇을 채우라는지 알 수 없었고, 서명란('(군) 단체장 (직인)')까지 요청이 됐다.
    블록 모양은 실물 공고를 본떴다(실제 기관 파일은 공개 저장소에 넣지 않는다)."""
    from app.services.guideline import parse_outline

    def p(i, t):
        return {"i": i, "page": 0, "kind": "para", "text": t, "rows": None}

    def tb(i, *rows):
        return {"i": i, "page": 0, "kind": "table", "text": " ".join(" ".join(r) for r in rows), "rows": [list(r) for r in rows]}

    blocks = [p(0, "Ⅰ. 사업 개요"), p(1, "1. 지역 여건"),
              p(2, "◦ 재래시장, 전통 5일장 등 운영 현황"),
              tb(3, ("읍·면", "명칭", "이용현황", "소재지", "비 고"), ("○○읍", "ㅇㅇ시장", "연 00명", "", "")),
              p(4, "2. 지방비 확보"), p(5, "□ 지방비 확약내역"), p(6, "(단위 : 백만원)"),
              tb(7, ("구분", "합계", "국비", "시도비", "군비", "비고"), ("확약내역", "", "", "", "", "")),
              p(8, "○○부 장관 귀하"),
              tb(9, ("붙임 7", "추가 보충 및 증빙자료")),
              p(10, "2025. 00. 00."),
              tb(11, ("(군) 단체장 (직인)", "(광역시도) 단체장 (직인)"))]
    items = parse_outline(blocks)["items"]
    needs = [n["text"] for it in items for n in it["needs"] if n["source"] == "표"]
    assert needs == ["재래시장, 전통 5일장 등 운영 현황 — 표: 읍·면 · 명칭 · 이용현황 · 소재지 · 비 고",
                     "지방비 확약내역 — 표: 구분 · 합계 · 국비 · 시도비 · 군비 · 비고",   # '(단위…)' 줄은 이름이 아니다
                     "붙임 7 · 추가 보충 및 증빙자료"]                                     # 붙임 제목 띠는 앞 줄을 달지 않는다
