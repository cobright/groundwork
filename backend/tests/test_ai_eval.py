# -*- coding: utf-8 -*-
"""AI 품질 시험 묶음(evals/ai_eval.py)의 채점이 맞는지 — 실제 AI 없이.

'잘하는 가짜 AI'로 돌리면 전부 통과, '환각하는 가짜 AI'로 돌리면 전부 실패해야 한다.
그래야 실제 AI 로 돌렸을 때의 점수를 믿을 수 있다.
"""
import json

import pytest

from evals import ai_eval


class Fake:
    name = "fake"

    def __init__(self, answer, model):
        self.answer, self.model = answer, model

    def complete(self, messages, **kw):
        return self.answer(messages[0].content, messages[-1].content)


def good(system, user):
    if "자료분석" in system:
        return json.dumps({"summary": "2026년 65세 이상 인구는 15,600명, 고령화율 37.1%.",
                           "key_points": ["독거노인 4,530명"], "usable_for": [], "cautions": []}, ensure_ascii=False)
    if "초고" in system:
        if "노인 인구 현황" in user:
            return "2026년 65세 이상 인구는 15,600명으로 고령화율은 37.1%다(근거: E-001)."
        if "기대 효과" in user:
            return "[확인 필요: 기대 효과를 잴 지표와 목표치]"
        return "군비 30% 매칭은 구두로만 협의했고 아직 확정되지 않았다(근거: E-002)."
    if "쪼개는" in system:
        raise RuntimeError("진술은 줄 단위 폴백으로")
    if "사실확인" in system:
        return json.dumps({"opinions": [{"severity": "중요", "target_text": "확보했다",
                                         "problem": "진술은 군비 매칭이 구두 협의로 미확정이라는데 본문은 확보했다고 단정함"}]},
                          ensure_ascii=False)
    if "가이드라인" in system:
        ids = [x["id"] for x in json.loads(user)["항목"]]
        return json.dumps({"items": [{"id": i, "question": "무엇을 답해야 하나?", "needs": []} for i in ids]},
                          ensure_ascii=False)
    return ""


def bad(system, user):
    if "자료분석" in system:
        return json.dumps({"summary": "65세 이상 인구 99,999명", "key_points": [], "usable_for": [], "cautions": []},
                          ensure_ascii=False)
    if "초고" in system:
        if "노인 인구 현황" in user:
            return "### 1. 노인 인구 현황\n65세 이상 인구는 **16,000명**이다(근거: E-009)."
        if "기대 효과" in user:
            return "이용자가 20% 늘어날 것이다."
        return "군비 30% 매칭을 확보했다(근거: E-002)."
    if "쪼개는" in system:
        raise RuntimeError("폴백")
    if "사실확인" in system:
        return json.dumps({"opinions": []})
    return "JSON 아님"


def _installer(monkeypatch, answer):
    from app.agents import critique, fact_check, structure, technical
    from app.skills import draft_writing, guideline_analysis, resource_analysis, statement
    fp = Fake(answer, "fake-model")

    def install():
        for m in (resource_analysis, draft_writing, statement, guideline_analysis,
                  fact_check, structure, technical, critique):
            monkeypatch.setattr(m, "get_provider", lambda *a, **k: fp)
    return install


def test_잘하는_AI는_전부_통과한다(monkeypatch, tmp_path):
    rep = ai_eval.run(install_fake=_installer(monkeypatch, good))
    assert [(c["id"], c["ok"]) for c in rep["cases"]] == [
        ("C1", True), ("C2", True), ("C3", True), ("C4", True), ("C5", True), ("C6", True), ("C7", True)], rep["cases"]


def test_환각하는_AI는_전부_걸린다(monkeypatch):
    rep = ai_eval.run(install_fake=_installer(monkeypatch, bad))
    got = {c["id"]: c for c in rep["cases"]}
    assert [c["ok"] for c in rep["cases"]] == [False] * 7, rep["cases"]
    assert "99,999" in got["C1"]["detail"]
    assert "없는 근거 번호" in got["C2"]["detail"]
    assert "확보했다" in got["C4"]["detail"]
    assert "목차 제목을 되풀이" in got["C7"]["detail"]


def test_결과는_마크다운으로_남는다(monkeypatch):
    rep = ai_eval.run(install_fake=_installer(monkeypatch, good))
    md = ai_eval.to_markdown(rep)
    assert "7 / 7 통과" in md and "fake-model" in md and "| C4 |" in md


def test_실DB는_건드리지_않는다(monkeypatch):
    from app import db
    before = db.DB_PATH
    ai_eval.run(install_fake=_installer(monkeypatch, good))
    assert db.DB_PATH == before
