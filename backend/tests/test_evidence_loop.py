# -*- coding: utf-8 -*-
"""근거 고리 닫기(2026-11-24 평가의 1단계) — 회신 → 주장 후보(원문 인용) → 한 번에 채택 → 초고·점검 → 출처 표시.

예전엔 회신 하나를 근거로 쓰려면 분석 → 확정 → 주장 직접 쓰기 → 목차 연결의 네 단계였고,
실제 업무(#6)에서 '새 주장'이 그대로 남았다. 이 시험은 그 고리가 시스템 안에서 닫히는지 본다.
"""
import json
import sqlite3

import pytest

from app import db
from app.services import provenance
from app.services.evidence_check import check_text
from app.services.quote import quote_in, quote_state
from app.skills import draft_writing, resource_analysis

NEED = "읍·면별 65세 이상 인구"
REPLY = ("<table><tr><td>구분</td><td>65세 이상 인구</td></tr>"
         "<tr><td>가온읍</td><td>4,210명</td></tr><tr><td>나루면</td><td>1,880명</td></tr></table>"
         "<p>경로당은 총 42개소이며 2025년 12월 기준입니다.</p>")
ANALYSIS = json.dumps({
    "summary": "읍·면별 고령인구와 경로당 수.",
    "key_points": ["요청한 읍·면별 65세 이상 인구: 가온읍 4,210명"], "usable_for": [], "cautions": [],
    "claims": [
        {"claim": "가온읍의 65세 이상 인구는 4,210명이다", "quote": "가온읍 │ 4,210명", "answers": NEED},
        {"claim": "경로당은 42개소다", "quote": "경로당은 총 42개소이며 2025년 12월 기준입니다.", "answers": ""},
        {"claim": "경로당 이용률이 높다", "quote": "경로당 이용률은 매우 높은 편이다", "answers": ""},  # 원문에 없는 인용
    ]}, ensure_ascii=False)


@pytest.fixture
def reply(client, project, fake_ai):
    """목차 n1 을 위한 자료요청 → 파일 회신 → 분석(주장 후보 셋, 하나는 원문에 없는 인용)."""
    fake_ai(ANALYSIS, resource_analysis)
    client.put(f"/api/projects/{project}/outline", json={"nodes": [
        {"uid": "n1", "sort": 0, "title": "고령인구 현황"}, {"uid": "n2", "sort": 1, "title": "추진 계획"}]})
    q = client.post(f"/api/projects/{project}/requests",
                    json={"need": NEED, "status": "요청함", "node_uid": "n1"}).json()
    r = client.post(f"/api/projects/{project}/requests/{q['id']}/received-file",
                    params={"filename": "회신.html"}, content=REPLY.encode())
    assert r.status_code == 201, r.text
    rid = r.json()["resource_id"]
    a = client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    assert a.status_code == 200, a.text
    return {"c": client, "pid": project, "rid": rid, "analysis": a.json()}


# ── 원문 인용: 같다고 보는 기준 ────────────────────────────────
def test_인용은_공백과_표_구분자만_무시한다():
    src = "가온읍 │ 4,210명\n경로당은 총 42개소이며"
    assert quote_in("가온읍 4,210명", src)           # 표 한 줄을 옮기며 구분자가 빠졌다
    assert quote_in("경로당은  총\n42개소", src)       # 줄바꿈·공백 차이
    assert not quote_in("가온읍 4,200명", src)        # 숫자가 다르면 다르다
    assert not quote_in("경로당이 총 42개소", src)     # 조사가 달라도 다르다 — 비슷하면 인용이 아니다
    assert quote_state("", src) == "없음"


# ── ① 주장 후보 ─────────────────────────────────────────────
def test_분석은_주장_후보를_내고_인용이_원문에_있는지_붙인다(reply):
    claims = reply["analysis"]["claims"]
    assert [x["quote_state"] for x in claims] == ["일치", "일치", "불일치"]
    assert claims[0]["answers"] == NEED


def test_자료_본문을_고치면_인용_판정이_따라_바뀐다(reply):
    s = reply
    res = next(x for x in s["c"].get(f"/api/projects/{s['pid']}/resources").json() if x["id"] == s["rid"])
    s["c"].put(f"/api/projects/{s['pid']}/resources/{s['rid']}",
               json={**{k: res[k] for k in ("name", "kind", "source_org", "base_date", "trust", "note")},
                     "text": res["text"].replace("4,210", "4,300")})
    res = next(x for x in s["c"].get(f"/api/projects/{s['pid']}/resources").json() if x["id"] == s["rid"])
    assert res["analysis"]["claims"][0]["quote_state"] == "불일치"


# ── ② 한 번에 채택 ──────────────────────────────────────────
def test_한_번에_채택하면_확정되고_요청의_목차로_이어진다(reply):
    s = reply
    picks = [{"claim": x["claim"], "quote": x["quote"]} for x in s["analysis"]["claims"]]
    r = s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/adopt", json={"claims": picks})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 3 and out["node_uid"] == "n1" and out["linked_from_request"] == NEED
    assert out["analysis"]["state"] == "사용자 확정"
    ev = out["evidence"]
    assert [e["status"] for e in ev] == ["확인", "확인", "확인 필요"]     # 인용이 원문에 없으면 '확인'으로 올리지 않는다
    assert [e["quote_state"] for e in ev] == ["일치", "일치", "불일치"]
    assert all(e["ev_no"].startswith("E-") and e["node_uid"] == "n1" for e in ev)
    # 두 번 눌러도 같은 근거를 또 만들지 않는다
    again = s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/adopt", json={"claims": picks}).json()
    assert again["created"] == 0 and again["skipped"] == 3


def test_고른_목차가_있으면_그쪽으로_잇는다(reply):
    s = reply
    x = s["analysis"]["claims"][1]
    r = s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/adopt",
                    json={"claims": [x], "node_uid": "n2"}).json()
    assert r["node_uid"] == "n2" and r["evidence"][0]["node_uid"] == "n2"


def test_요청과_다른_회신은_채택도_확정처럼_묻는다(client, project, fake_ai):
    fake_ai(json.dumps({"summary": "다른 자료", "key_points": [], "usable_for": [],
                        "cautions": [f"요청한 {NEED}은(는) 이 자료에 없습니다 — 추가 요청 필요"],
                        "claims": [{"claim": "기금 72억 원", "quote": "72억 원"}]}, ensure_ascii=False),
            resource_analysis)
    q = client.post(f"/api/projects/{project}/requests", json={"need": NEED, "status": "요청함"}).json()
    rid = client.post(f"/api/projects/{project}/requests/{q['id']}/received-file", params={"filename": "x.html"},
                      content="<table><tr><td>기본배분 72억 원</td></tr></table>".encode()).json()["resource_id"]
    client.post(f"/api/projects/{project}/resources/{rid}/analyze", json={})
    pick = {"claims": [{"claim": "기금 72억 원", "quote": "72억 원"}]}
    r = client.post(f"/api/projects/{project}/resources/{rid}/adopt", json=pick)
    assert r.status_code == 409 and "요청한 것 1가지" in r.json()["detail"]
    assert client.get(f"/api/projects/{project}/evidence").json() == []      # 묻는 동안 아무것도 만들지 않는다
    assert client.post(f"/api/projects/{project}/resources/{rid}/adopt",
                       json={**pick, "force": True}).status_code == 200


def test_분석_전_자료는_채택할_수_없다(client, project):
    rid = client.post(f"/api/projects/{project}/resources", json={"name": "a", "text": "b"}).json()["id"]
    r = client.post(f"/api/projects/{project}/resources/{rid}/adopt", json={"claims": [{"claim": "x"}]})
    assert r.status_code == 400


def test_근거를_고칠_때_인용을_보내지_않으면_그대로_둔다(reply):
    """옛 화면(인용 칸이 없는)으로 근거를 고쳐도 인용이 지워지지 않는다."""
    s = reply
    x = s["analysis"]["claims"][0]
    e = s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/adopt", json={"claims": [x]}).json()["evidence"][0]
    body = {k: e[k] for k in ("claim", "resource_id", "locator", "trust", "status", "node_uid")}
    got = s["c"].put(f"/api/projects/{s['pid']}/evidence/{e['id']}", json={**body, "claim": "고친 주장"}).json()
    assert got["quote"] == x["quote"] and got["claim"] == "고친 주장"


# ── ③ 초고는 인용을 받고, 점검기는 인용을 대조한다 ─────────────────────
def test_초고에는_요약이_아니라_원문_인용이_넘어간다(reply, fake_ai):
    s = reply
    s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/adopt", json={"claims": s["analysis"]["claims"][:1]})
    fp = fake_ai("가온읍의 65세 이상 인구는 4,210명이다. (근거: E-001)", draft_writing)
    r = s["c"].post(f"/api/projects/{s['pid']}/nodes/n1/draft/generate", json={"strictness": "엄격"})
    assert r.status_code == 200, r.text
    prompt = fp.calls[0][1].content
    assert "원문 인용: “가온읍 │ 4,210명”" in prompt
    assert "자료요약" not in prompt          # 인용이 있으면 AI 요약을 함께 넘기지 않는다
    assert r.json()["check"] == []


def test_점검기는_인용이_원문에_없는_근거와_따옴표_글을_짚는다(reply):
    s = reply
    s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/adopt", json={"claims": s["analysis"]["claims"]})
    from app.services.evidence_check import evidence_index
    with db.connect() as c:
        index = evidence_index(c, s["pid"])
    kinds = lambda t: [f["kind"] for f in check_text(t, index)]
    assert "인용이 원문에 없는 근거" in kinds("경로당 이용률이 높다. (근거: E-003)")
    assert kinds("경로당은 “총 42개소”이다. (근거: E-002)") == []
    assert "따옴표 안 글이 원문에 없음" in kinds("담당 부서는 “경로당 신축이 시급하다”고 했다. (근거: E-002)")
    # 작은따옴표는 강조로 흔히 쓴다 — 짚지 않는다
    assert kinds("경로당은 '생활 거점'으로 총 42개소다. (근거: E-002)") == []


def test_최종본_점검과_부록에_원문_인용이_나온다(reply):
    s = reply
    s["c"].post(f"/api/projects/{s['pid']}/resources/{s['rid']}/adopt", json={"claims": s["analysis"]["claims"]})
    items = s["c"].get(f"/api/projects/{s['pid']}/final-check").json()["items"]
    bad = next(i for i in items if i["label"] == "원문 인용이 자료 본문에 없는 근거")
    assert any(d.startswith("E-003") for d in bad["detail"])


# ── ④ 본문 이력과 출처 표시 ─────────────────────────────────────
def test_문장마다_AI_그대로_고침_직접을_가린다():
    ai = ["가온읍의 65세 이상 인구는 4,210명이다. 경로당은 42개소로 부족하다."]
    body = ("가온읍의 65세 이상 인구는 4,210명이다. 경로당은 42개소로 많이 부족하다. "
            "주민 설명회를 두 차례 열었다.")
    got = provenance.classify(body, ai)
    assert [x["origin"] for x in got["sentences"]] == ["AI 그대로", "사람이 고침", "사람이 씀"]
    assert got["counts"] == {"AI 그대로": 1, "사람이 고침": 1, "사람이 씀": 1}


def test_초고_생성과_본문_저장이_이력에_남고_출처가_돌아온다(client, project, fake_ai):
    client.put(f"/api/projects/{project}/outline", json={"nodes": [{"uid": "n1", "sort": 0, "title": "현황"}]})
    fake_ai("인구가 줄었다. 고령화가 빠르다.", draft_writing)
    client.post(f"/api/projects/{project}/nodes/n1/draft/generate", json={"strictness": "유연"})
    r = client.put(f"/api/projects/{project}/nodes/n1/draft", json={"body": "인구가 줄었다. 설명회를 열었다."}).json()
    assert r["provenance"]["counts"] == {"AI 그대로": 1, "사람이 고침": 0, "사람이 씀": 1}
    # 타자를 멈출 때마다 저장해도 이력은 한 줄로 묶인다
    client.put(f"/api/projects/{project}/nodes/n1/draft", json={"body": "인구가 줄었다. 설명회를 두 번 열었다."})
    hist = client.get(f"/api/projects/{project}/nodes/n1/draft/history").json()
    assert [h["origin"] for h in hist] == ["본문", "AI 제안"]
    assert hist[0]["body"].endswith("두 번 열었다.")
    assert client.get(f"/api/projects/{project}/nodes/n1/draft").json()["provenance"]["counts"]["AI 그대로"] == 1


def test_목차에서_사라졌다_되살아나도_이력은_남는다(client, project, fake_ai):
    """되돌리기가 본문을 살렸는데 이력이 없으면 모든 문장이 '사람이 씀'으로 보인다(출처 표시가 거짓)."""
    client.put(f"/api/projects/{project}/outline", json={"nodes": [{"uid": "n1", "sort": 0, "title": "현황"}]})
    fake_ai("인구가 줄었다.", draft_writing)
    client.post(f"/api/projects/{project}/nodes/n1/draft/generate", json={"strictness": "유연"})
    client.put(f"/api/projects/{project}/nodes/n1/draft", json={"body": "인구가 줄었다."})
    client.put(f"/api/projects/{project}/outline", json={"nodes": []})
    sid = client.get(f"/api/projects/{project}/outline/snapshots").json()[0]["id"]
    client.post(f"/api/projects/{project}/outline/snapshots/{sid}/restore")
    d = client.get(f"/api/projects/{project}/nodes/n1/draft").json()
    assert d["draft"]["body"] == "인구가 줄었다." and d["provenance"]["counts"]["AI 그대로"] == 1


# ── 마이그레이션 ────────────────────────────────────────────
def test_구스키마_DB에_인용_칸을_더해도_근거가_남는다(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL DEFAULT '',
            doc_type TEXT NOT NULL DEFAULT '', purpose TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE resource_analysis (resource_id INTEGER PRIMARY KEY, summary TEXT NOT NULL DEFAULT '',
            key_points TEXT NOT NULL DEFAULT '[]', usable_for TEXT NOT NULL DEFAULT '[]', cautions TEXT NOT NULL DEFAULT '[]',
            state TEXT NOT NULL DEFAULT '분석 전', model TEXT NOT NULL DEFAULT '', analyzed_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE evidence (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            claim TEXT NOT NULL DEFAULT '', resource_id INTEGER, locator TEXT NOT NULL DEFAULT '',
            trust TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '확인 필요', node_uid TEXT,
            created_at TEXT NOT NULL);
        INSERT INTO projects(name, created_at, updated_at) VALUES('옛 업무', '2026-01-01', '2026-01-01');
        INSERT INTO resource_analysis(resource_id, summary, state) VALUES(7, '옛 요약', '사용자 확정');
        INSERT INTO evidence(project_id, claim, locator, created_at) VALUES(1, '옛 주장', '3쪽', '2026-01-01');
    """)
    old.commit(); old.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(db, "BACKUP_DIR", tmp_path / "backups")
    db.init_db(); db.init_db()                       # 두 번 돌아도 같다
    with db.connect() as c:
        e = dict(c.execute("SELECT * FROM evidence").fetchone())
        a = dict(c.execute("SELECT * FROM resource_analysis").fetchone())
        assert c.execute("SELECT name FROM sqlite_master WHERE name='draft_versions'").fetchone()
    assert (e["claim"], e["locator"], e["quote"]) == ("옛 주장", "3쪽", "")
    assert (a["summary"], a["state"], a["claims"]) == ("옛 요약", "사용자 확정", "[]")
