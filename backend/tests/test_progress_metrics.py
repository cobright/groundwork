# -*- coding: utf-8 -*-
"""진보 지표 — 실DB 를 읽기만 하고, 근거 고리·출처·검토 헛지적 대리 지표를 센다."""
import hashlib

from app import db
from app.skills import draft_writing
from evals import progress_metrics


def _digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_지표를_세고_원본_DB는_건드리지_않는다(client, project, fake_ai):
    c = client
    c.put(f"/api/projects/{project}/outline", json={"nodes": [
        {"uid": "a", "sort": 0, "title": "현황"}, {"uid": "b", "sort": 1, "title": "계획"}]})
    rid = c.post(f"/api/projects/{project}/resources", json={"name": "통계", "text": "경로당은 총 42개소이다."}).json()["id"]
    with db.connect() as cn:      # 분석을 거친 것처럼(가짜 AI 없이) — 채택에는 분석 행이 필요하다
        cn.execute("INSERT INTO resource_analysis(resource_id,summary,state) VALUES(?,?,?)", (rid, "요약", "분석 완료"))
    c.post(f"/api/projects/{project}/resources/{rid}/adopt",
           json={"claims": [{"claim": "경로당 42개소", "quote": "경로당은 총 42개소"}], "node_uid": "a"})
    c.post(f"/api/projects/{project}/evidence", json={"claim": "", "node_uid": "b"})          # 빈 주장
    fake_ai("경로당은 42개소다. (근거: E-001)", draft_writing)
    c.post(f"/api/projects/{project}/nodes/a/draft/generate", json={"strictness": "엄격"})
    c.put(f"/api/projects/{project}/nodes/a/draft",
          json={"body": "경로당은 42개소다. (근거: E-001)\n주민 설명회를 열었다."})
    with db.connect() as cn:
        cn.execute("INSERT INTO review_opinions(project_id,node_uid,kind,severity,problem,status,source,created_at) "
                   "VALUES(?,?,?,?,?,?,?,?)", (project, "a", "사실확인", "중요", "x", "반영안함", "AI", "t"))
        cn.execute("INSERT INTO review_opinions(project_id,node_uid,kind,severity,problem,status,source,created_at) "
                   "VALUES(?,?,?,?,?,?,?,?)", (project, "a", "사실확인", "중대", "y", "반영", "AI", "t"))

    path = db.DB_PATH
    before = _digest(path)
    m = progress_metrics.run(path)
    assert _digest(path) == before and db.DB_PATH == path       # 원본은 그대로, 경로도 되돌린다

    t = m["total"]
    assert (t["bodies"], t["nodes"], t["sents"], t["cited"], t["cited_ok"]) == (1, 2, 2, 1, 1)
    assert (t["evidence"], t["quoted"], t["quote_ok"], t["adopted"], t["blank"]) == (2, 1, 1, 1, 1)
    assert (t["prov_AI 그대로"], t["prov_사람이 씀"]) == (1, 1)
    assert (t["ops_closed"], t["ops_rejected"]) == (2, 1)
    md = progress_metrics.to_markdown(m, "시험")
    assert "| M2 | └ 원문 인용이 맞는 근거를 단 문장 | 1/1 (100%) |" in md
    assert "| M6 | AI 검토 중대·중요 의견 중 '반영안함' | 1/2 (50%)" in md


def test_보관함의_업무는_세지_않는다(client, project):
    with db.connect() as cn:
        cn.execute("UPDATE projects SET archived_at='2026-11-25' WHERE id=?", (project,))
    assert progress_metrics.run(db.DB_PATH)["projects"] == []
