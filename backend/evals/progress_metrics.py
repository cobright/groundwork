# -*- coding: utf-8 -*-
"""진보를 재는 숫자 — 실제 업무 DB 에서 잰다. **읽기만** 한다(실DB 를 임시 사본으로 떠서 그 사본을 연다).

왜(2026-11-24 평가 5장 '지금부터 기록 권장'):
  기능이 사용보다 앞서 있다. 기능을 더할 때마다 '실제로 나아졌는가'를 같은 잣대로 재야
  다음에 무엇을 고칠지 추측이 아니라 기록으로 정한다. 품질 시험(ai_eval)이 모의데이터로 AI 를 잰다면,
  이것은 **사람이 실제로 쓴 업무**를 잰다. AI 를 부르지 않는다 — 요금이 들지 않는다.

무엇을 재는가(보관함에 든 업무는 뺀다):
  M1 확정 본문이 있는 목차 수                  — 도구로 실제로 문서를 쓰고 있는가
  M2 본문 문장 중 근거 번호를 단 문장 · 그중 원문 인용이 맞는 근거를 단 문장 — 근거 고리가 닫혔는가
  M3 근거 중 원문 인용이 붙은 근거 · 채택(한 번에)으로 만든 근거(추정) · 주장이 빈 근거
  M4 본문 문장의 출처: AI 그대로 / 사람이 고침 / 사람이 씀      — 원칙 1 이 실제로 어떻게 쓰이는가
  M5 근거 점검기 의견 수(본문)                  — 헛경보인지는 사람이 본다(여기선 세기만)
  M6 AI 검토의 중대·중요 의견 중 사람이 '반영안함'으로 닫은 몫 — 검토 헛지적의 대리 지표

돌리는 법(개발 PC 또는 행정망 PC — 표준 라이브러리 + 앱 코드만 쓴다):
    cd backend
    python -m evals.progress_metrics          # 화면에 찍고 evals/results/metrics_날짜.md 로 남긴다
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "0/0"


def measure(c) -> dict:
    """열린 연결(c)에서 지표를 잰다. 업무별 + 합계."""
    from app.services import provenance
    from app.services.evidence_check import _cites, check_text, evidence_index, split_sentences
    from app.services.numbering import sections_with_body
    from app.services.quote import quote_state

    rows, tot = [], {}

    def add(k, v):
        tot[k] = tot.get(k, 0) + v

    for p in c.execute("SELECT id, name FROM projects WHERE archived_at='' ORDER BY id").fetchall():
        pid = p["id"]
        secs = sections_with_body(c, pid)
        bodies = [s for s in secs if (s["body"] or "").strip()]
        index = evidence_index(c, pid)
        evs = [dict(e) for e in c.execute("SELECT * FROM evidence WHERE project_id=?", (pid,))]
        texts = {}
        for e in evs:
            if e["resource_id"] and e["resource_id"] not in texts:
                r = c.execute("SELECT text FROM resources WHERE id=?", (e["resource_id"],)).fetchone()
                texts[e["resource_id"]] = r["text"] if r else ""
        quoted = [e for e in evs if (e.get("quote") or "").strip()]
        quote_ok = {e["id"] for e in quoted if e["resource_id"]
                    and quote_state(e["quote"], texts.get(e["resource_id"], "")) == "일치"}
        from app.services.numbering import evidence_numbers
        nos = evidence_numbers(c, pid)
        ok_nos = {nos[i] for i in quote_ok if i in nos}

        sents = cited = cited_ok = findings = 0
        prov = {provenance.AI: 0, provenance.EDITED: 0, provenance.HUMAN: 0}
        for s in bodies:
            ss = split_sentences(s["body"])
            sents += len(ss)
            for x in ss:
                cs = _cites(x)
                if cs:
                    cited += 1
                    if any(n in ok_nos for n in cs):
                        cited_ok += 1
            findings += len(check_text(s["body"], index))
            for k, v in provenance.for_node(c, pid, s["uid"], s["body"])["counts"].items():
                prov[k] += v
        # 채택으로 만든 근거(추정): 인용이 붙고 위치(locator)가 빈 문서 근거 — adopt 가 그렇게 만든다
        adopted = sum(1 for e in quoted if not (e.get("locator") or "").strip())
        blank = sum(1 for e in evs if not (e.get("claim") or "").strip())
        ops = c.execute("SELECT status FROM review_opinions WHERE project_id=? AND source='AI' "
                        "AND severity IN ('중대','중요')", (pid,)).fetchall()
        closed = [o for o in ops if o["status"] not in ("미처리", "확인중")]
        rejected = [o for o in closed if o["status"] == "반영안함"]

        row = {"id": pid, "name": p["name"], "nodes": len(secs), "bodies": len(bodies),
               "sents": sents, "cited": cited, "cited_ok": cited_ok,
               "evidence": len(evs), "quoted": len(quoted), "quote_ok": len(quote_ok), "adopted": adopted,
               "blank": blank, "findings": findings, **{f"prov_{k}": v for k, v in prov.items()},
               "ops": len(ops), "ops_closed": len(closed), "ops_rejected": len(rejected)}
        rows.append(row)
        for k, v in row.items():
            if isinstance(v, int) and k != "id":
                add(k, v)
    return {"projects": rows, "total": tot}


def to_markdown(m: dict, when: str) -> str:
    t = m["total"]
    g = lambda k: t.get(k, 0)  # noqa: E731
    prov_all = g("prov_AI 그대로") + g("prov_사람이 고침") + g("prov_사람이 씀")
    out = [f"# 진보 지표 — {when}", "",
           f"활성 업무 {len(m['projects'])}건 · 실DB 를 읽기만 했다(사본).", "",
           "| | 지표 | 값 |", "|---|---|---|",
           f"| M1 | 확정 본문이 있는 목차 | {g('bodies')} / 목차 {g('nodes')} |",
           f"| M2 | 근거 번호를 단 문장 | {_pct(g('cited'), g('sents'))} |",
           f"| M2 | └ 원문 인용이 맞는 근거를 단 문장 | {_pct(g('cited_ok'), g('cited'))} |",
           f"| M3 | 원문 인용이 붙은 근거 | {_pct(g('quoted'), g('evidence'))} (인용이 원문과 일치 {g('quote_ok')}) |",
           f"| M3 | └ 한 번에 채택으로 만든 근거(추정) | {g('adopted')} |",
           f"| M3 | 주장이 빈 근거 | {g('blank')} |",
           f"| M4 | 본문 문장 출처 AI 그대로 / 고침 / 씀 | {g('prov_AI 그대로')} / {g('prov_사람이 고침')} / "
           f"{g('prov_사람이 씀')} (문장 {prov_all}) |",
           f"| M5 | 근거 점검기 의견(본문) | {g('findings')} |",
           f"| M6 | AI 검토 중대·중요 의견 중 '반영안함' | {_pct(g('ops_rejected'), g('ops_closed'))} (처리한 것 기준, 전체 {g('ops')}) |",
           "", "## 업무별", "",
           "| 업무 | 본문 목차 | 문장 | 근거 단 문장 | 근거 | 인용 근거 | 점검 의견 |", "|---|---|---|---|---|---|---|"]
    for r in m["projects"]:
        out.append(f"| #{r['id']} {r['name'][:24]} | {r['bodies']}/{r['nodes']} | {r['sents']} | {r['cited']} | "
                   f"{r['evidence']} | {r['quoted']} | {r['findings']} |")
    out += ["", "읽는 법: M1 이 0 이면 나머지는 의미가 없다 — 도구로 실제 문서를 쓰고 있지 않다는 뜻이다.",
            "M6 은 사람이 '반영안함'으로 닫은 몫이라 헛지적의 대리 지표일 뿐이다(사유는 검토 화면의 메모에)."]
    return "\n".join(out) + "\n"


def run(db_path: Path | None = None) -> dict:
    """실DB(또는 주어진 DB)를 임시 사본으로 떠서 잰다. 원본은 읽기 전용으로만 연다."""
    from app import db
    src_path = Path(db_path or db.DB_PATH)
    tmp = Path(tempfile.mkdtemp(prefix="wb_metrics_")) / "copy.db"
    src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        src.close(); dst.close()
    real = db.DB_PATH
    try:
        db.DB_PATH = tmp
        db.init_db()                     # 사본이 옛 구조면 사본에서만 올린다(원본은 그대로)
        with db.connect() as c:
            return measure(c)
    finally:
        db.DB_PATH = real


def main(argv=None):
    from app import db
    if not Path(db.DB_PATH).exists():
        print("업무 DB 가 없습니다:", db.DB_PATH)
        return 1
    m = run()
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    md = to_markdown(m, when)
    outdir = BACKEND / "evals" / "results"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    path.write_text(md, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md.split("\n## ")[0])
    print(f"자세한 것: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
