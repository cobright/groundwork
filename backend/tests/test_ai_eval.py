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
        # 원문에서 숫자가 든 줄 하나를 그대로 옮긴다(C8 — 인용은 글자 그대로)
        body = user.split("[자료 본문]", 1)[-1]
        line = next(ln.strip() for ln in body.splitlines() if any(ch.isdigit() for ch in ln) and len(ln.strip()) > 6)
        if "노인인구" in user:               # 가온군 회신(C1) — 원문에 있는 값만 요약한다
            summary, points = "2026년 65세 이상 인구는 15,600명, 고령화율 37.1%.", ["독거노인 4,530명"]
        else:                                 # 창업지원(C10) — 옮긴 줄을 그대로 요약으로
            summary, points = line, [line]
        return json.dumps({"summary": summary, "key_points": points, "usable_for": [], "cautions": [],
                           "claims": [{"claim": "자료의 핵심 수치", "quote": line}]}, ensure_ascii=False)
    if "초고" in system:
        if "시장 규모" in user:              # C10 — 받은 원문 인용을 그대로 옮긴다
            q = user.split("원문 인용: “", 1)[1].split("”", 1)[0]
            return f"{q.replace('│', ' ')}. (근거: E-001)"
        if "노인 인구 현황" in user:
            return "2026년 65세 이상 인구는 15,600명으로 고령화율은 37.1%다(근거: E-001)."
        if "기대 효과" in user:
            return "[확인 필요: 기대 효과를 잴 지표와 목표치]"
        return "군비 30% 매칭은 구두로만 협의했고 아직 확정되지 않았다(근거: E-002)."
    if "쪼개는" in system:
        raise RuntimeError("진술은 줄 단위 폴백으로")
    if "사실확인" in system:
        if "확보했다" not in user:           # C9 — 맞는 본문에는 짚을 것이 없다
            return json.dumps({"opinions": []})
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
        return json.dumps({"summary": "65세 이상 인구 99,999명", "key_points": [], "usable_for": [], "cautions": [],
                           "claims": [{"claim": "인구가 많다", "quote": "65세 이상 인구가 매우 많은 편이다"}]},
                          ensure_ascii=False)
    if "초고" in system:
        if "시장 규모" in user:
            return "시장 규모는 9,999억 원이다(근거: E-001)."
        if "노인 인구 현황" in user:
            return "### 1. 노인 인구 현황\n65세 이상 인구는 **16,000명**이다(근거: E-009)."
        if "기대 효과" in user:
            return "이용자가 20% 늘어날 것이다."
        return "군비 30% 매칭을 확보했다(근거: E-002)."
    if "쪼개는" in system:
        raise RuntimeError("폴백")
    if "사실확인" in system:
        if "확보했다" in user:               # 함정은 놓치고(C5)
            return json.dumps({"opinions": []})
        return json.dumps({"opinions": [{"severity": "중대", "target_text": "15,600명",   # 맞는 문장을 짚는다(C9)
                                         "problem": "인구 수치가 근거와 다릅니다"}]}, ensure_ascii=False)
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
        ("C1", True), ("C2", True), ("C3", True), ("C4", True), ("C5", True), ("C6", True), ("C7", True),
        ("C8", True), ("C9", True), ("C10", True)], rep["cases"]
    # 인용이 맞는 후보가 있으면 C2 는 '한 번에 채택'으로 만든 근거(원문 인용)로 초고를 쓴다
    assert next(c for c in rep["cases"] if c["id"] == "C2")["note"].startswith("채택 길")


def test_환각하는_AI는_전부_걸린다(monkeypatch):
    rep = ai_eval.run(install_fake=_installer(monkeypatch, bad))
    got = {c["id"]: c for c in rep["cases"]}
    assert [c["ok"] for c in rep["cases"]] == [False] * 10, rep["cases"]
    assert "99,999" in got["C1"]["detail"]
    assert "없는 근거 번호" in got["C2"]["detail"]
    assert "확보했다" in got["C4"]["detail"]
    assert "목차 제목을 되풀이" in got["C7"]["detail"]
    assert "인용이 원문에 없음" in got["C8"]["detail"]
    assert got["C2"]["note"].startswith("인용 후보 없음")
    assert "헛지적" in got["C9"]["detail"] and "인구 수치가 근거와 다릅니다" in got["C9"]["detail"]
    assert "분석이 지어낸 숫자" in got["C10"]["detail"]       # 인용이 다 틀리면 예전 길로 C2 를 잇는다


def test_결과는_마크다운으로_남는다(monkeypatch):
    rep = ai_eval.run(install_fake=_installer(monkeypatch, good))
    md = ai_eval.to_markdown(rep)
    assert "10 / 10 통과" in md and "fake-model" in md and "| C4 |" in md


def test_실DB는_건드리지_않는다(monkeypatch):
    from app import db
    before = db.DB_PATH
    ai_eval.run(install_fake=_installer(monkeypatch, good))
    assert db.DB_PATH == before
