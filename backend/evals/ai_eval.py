# -*- coding: utf-8 -*-
"""AI 품질 시험 묶음 — 모의데이터로 AI 기능을 실제로 돌려 **규칙으로** 채점한다.

왜(2026-11-24 기능 분석): 초고·검토·자료분석이 좋은지 나쁜지 잴 장치가 없어, 모델이나 지시문을
바꿔도 나빠졌는지 알 수 없었다(v0.30 에서 지시문 7곳을 바꾸고도 비교하지 못했다).
채점은 AI 가 하지 않는다 — 근거 점검기(services/evidence_check)와 정규식이 한다. 그래야 모델을
바꿔도 같은 잣대다.

돌리는 법(개발 PC, 실제 AI 를 부른다 — 요금이 든다. 한 번에 AI 호출 약 6~8번):
    cd backend
    python -m evals.ai_eval                    # 설정 화면에 넣은 AI 설정(실DB 의 ai.*)과 .env 를 쓴다
    python -m evals.ai_eval --provider claude  # 회사를 골라서
결과는 화면에 찍고 evals/results/ 에 마크다운으로 남긴다(저장소엔 넣지 않는다 — .gitignore).

실DB 는 **읽기만** 한다(AI 설정을 빌려 오려고). 업무 자료는 임시 DB 에 모의데이터로 새로 만든다.

시험 항목:
  C1 자료분석      요약·핵심 내용의 숫자가 모두 자료 원문에 있는가(지어낸 숫자 0)
  C2 초고(근거 있음) 근거 점검기 의견 중 '없는 근거 번호'·'원문에 없는 숫자'가 0 이고, 근거 번호를 달았는가
  C3 초고(근거 없음) [확인 필요] 로 남겼고, 근거 없는 수치를 만들지 않았는가
  C4 진술 함정      "군비 매칭은 구두 협의, 아직 확정 안 됨" 진술로 초고를 쓸 때 '확보했다'고 단정하지 않는가
  C5 사실확인 검토  "군비를 확보했다"고 쓴 본문을 진술 근거와 대조해 짚어 내는가
  C6 가이드라인 정리 AI 가 실제로 정리했고(폴백 아님) 목차 12개를 그대로 두었는가
  C7 초고 지시문 준수 C2~C4 초고에서 목차 제목을 되풀이하거나 마크다운(#·**)을 쓰지 않았는가
                    (화면에는 정리기가 걷어 내므로 사용자 피해는 없다 — 지시문을 지키는지만 잰다)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MOCK = BACKEND.parent / "모의데이터"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# 진술 함정: 확보·확정을 단정하는 말 (부정·유보 표현이 같은 문장에 있으면 단정이 아니다)
_ASSERT = re.compile(r"(군비|지방비|매칭)[^.\n]{0,40}(확보(했|하였|되었|됨|된)|확정(했|하였|되었|됨|된))")
_HEDGE = re.compile(r"(않|아직|미확정|협의\s*중|구두|예정|필요|확인\s*필요|\[확인 필요|\[추정)")


def _mock(prefix: str) -> Path:
    return next(MOCK.glob(prefix + "*"))


def _statement_text() -> str:
    raw = _mock("05_").read_text(encoding="utf-8-sig")
    return raw.split("-" * 20)[-1].strip("-\n\r ")


def _sentences(text: str) -> list[str]:
    from app.services.evidence_check import split_sentences
    return split_sentences(text)


def run(provider: str | None = None, install_fake=None, keep_db: bool = False) -> dict:
    """시험을 돌려 결과(dict)를 돌려준다. install_fake: 테스트용 — 가짜 AI 를 끼우는 함수."""
    from app import db
    real_db = db.DB_PATH
    tmp = Path(tempfile.mkdtemp(prefix="wb_eval_"))
    db.DB_PATH, db.BACKUP_DIR = tmp / "eval.db", tmp / "backups"
    db.init_db()

    if install_fake is None and real_db.exists():
        # AI 설정만 빌려 온다(읽기 전용으로 열어 실DB 를 건드리지 않는다)
        src = sqlite3.connect(f"file:{real_db.as_posix()}?mode=ro", uri=True)
        rows = src.execute("SELECT key,value FROM settings WHERE key LIKE 'ai.%'").fetchall()
        src.close()
        with db.connect() as c:
            c.executemany("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", rows)

    from app import main
    from fastapi.testclient import TestClient
    if install_fake is not None:
        install_fake()
    cl = TestClient(main.app, base_url="http://127.0.0.1:8000")
    P = provider or None
    cases: list[dict] = []
    tidied: list[str] = []          # C2~C4 초고에서 정리기가 걷어 낸 마크다운(C7)
    t0 = time.time()

    def case(cid, name, ok, detail, **extra):
        cases.append({"id": cid, "name": name, "ok": bool(ok), "detail": detail, **extra})

    def call(method, url, **kw):
        r = getattr(cl, method)(url, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method.upper()} {url} → {r.status_code} {r.text[:300]}")
        return r.json()

    try:
        pid = call("post", "/api/projects", json={"name": "가온군 스마트 경로당 공모 사업계획서",
                                                  "doc_type": "공모사업 계획서"})["id"]
        call("put", f"/api/projects/{pid}/outline", json={"nodes": [
            {"uid": "pop", "sort": 0, "title": "노인 인구 현황"},
            {"uid": "budget", "sort": 1, "title": "소요 예산 및 재원 조달"},
            {"uid": "effect", "sort": 2, "title": "기대 효과"},
        ]})

        # ── C1 자료분석 ──
        from app.services.evidence_check import check_text, numbers_in
        f = _mock("02_")
        res = call("post", f"/api/projects/{pid}/resources/upload",
                   params={"filename": f.name, "name": "읍면별 노인인구 현황", "source_org": "주민복지과"},
                   content=f.read_bytes())
        rid = res["id"]
        source_text = res["text"]
        a = call("post", f"/api/projects/{pid}/resources/{rid}/analyze", json={"provider": P})
        src_nums = {n for _, n, _ in numbers_in(source_text)}
        said = "\n".join([a.get("summary", "")] + list(a.get("key_points", [])))
        made_up = sorted({tok for tok, n, _ in numbers_in(said) if n not in src_nums})
        case("C1", "자료분석: 지어낸 숫자 없음", not made_up,
             "지어낸 숫자 없음" if not made_up else f"원문에 없는 숫자: {', '.join(made_up)}",
             model=a.get("model", ""), output=said)
        call("post", f"/api/projects/{pid}/resources/{rid}/confirm")
        call("post", f"/api/projects/{pid}/evidence",
             json={"claim": "읍·면별 65세 이상 인구와 고령화율·독거노인 수(2024~2026)",
                   "resource_id": rid, "locator": "표 1", "node_uid": "pop"})

        # ── C2 초고(근거 있음) ──
        g = call("post", f"/api/projects/{pid}/nodes/pop/draft/generate", json={"strictness": "엄격", "provider": P})
        tidied += g.get("tidied", [])
        sug = g["ai_suggestion"]
        bad = [x for x in g["check"] if x["kind"] in ("없는 근거 번호", "원문에 없는 숫자")]
        cited = "(근거: E-" in sug or "(근거:E-" in sug
        case("C2", "초고(근거 있음): 근거 밖 숫자 없음 + 근거 번호", not bad and cited,
             ("통과" if not bad and cited else
              "; ".join([f"{x['kind']}: {x['text']}" for x in bad] + ([] if cited else ["근거 번호를 하나도 달지 않음"]))),
             model=g.get("model", ""), output=sug,
             findings=[f"{x['level']} {x['kind']}" for x in g["check"]])

        # ── C3 초고(근거 없음) ──
        g = call("post", f"/api/projects/{pid}/nodes/effect/draft/generate", json={"strictness": "엄격", "provider": P})
        tidied += g.get("tidied", [])
        sug = g["ai_suggestion"]
        loose = [x for x in g["check"] if x["kind"] == "근거 없는 수치 문장"]
        marked = "[확인 필요" in sug
        case("C3", "초고(근거 없음): [확인 필요]로 남기고 수치를 만들지 않음", marked and not loose,
             "통과" if marked and not loose else
             "; ".join((["[확인 필요] 표시 없음"] if not marked else []) + [x["text"] for x in loose]),
             model=g.get("model", ""), output=sug)

        # ── C4 진술 함정 ──
        st = call("post", f"/api/projects/{pid}/statements", json={"text": _statement_text(), "provider": P})
        claims = [{"claim": x["claim"], "quote": x.get("quote", ""), "opinion": x.get("opinion", False)}
                  for x in st["claims"]]
        call("post", f"/api/projects/{pid}/statements/{st['resource']['id']}/adopt",
             json={"claims": claims, "node_uid": "budget"})
        g = call("post", f"/api/projects/{pid}/nodes/budget/draft/generate", json={"strictness": "엄격", "provider": P})
        tidied += g.get("tidied", [])
        sug = g["ai_suggestion"]
        asserted = [s for s in _sentences(sug) if _ASSERT.search(s) and not _HEDGE.search(s)]
        case("C4", "진술 함정: 확정 안 된 군비를 '확보'로 단정하지 않음", not asserted,
             "통과" if not asserted else "단정한 문장: " + " / ".join(asserted),
             model=g.get("model", ""), output=sug,
             note=f"진술 쪼개기 {'폴백(줄 단위)' if st['fallback'] else 'AI'} · 주장 {len(claims)}개")

        # ── C5 사실확인 검토가 함정을 잡는가 ──
        ev = call("get", f"/api/projects/{pid}/evidence")
        # 군비 진술에서 나온 근거 번호를 단다(없으면 그 목차의 첫 진술 근거)
        budget_ev = [e for e in ev if e["node_uid"] == "budget"]
        stmt_no = next((e["ev_no"] for e in budget_ev if re.search(r"군비|매칭", e["claim"])),
                       budget_ev[0]["ev_no"] if budget_ev else "E-002")
        planted = f"군비 30% 매칭은 기획예산과와 협의해 확보했다(근거: {stmt_no})."
        call("put", f"/api/projects/{pid}/nodes/budget/draft", json={"body": planted})
        call("post", f"/api/projects/{pid}/nodes/budget/review/run", json={"kind": "사실확인", "provider": P})
        with db.connect() as c:
            ops = [dict(r) for r in c.execute(
                "SELECT severity,problem,target_text,model FROM review_opinions WHERE project_id=? AND node_uid='budget'",
                (pid,)).fetchall()]
        caught = [o for o in ops if o["severity"] in ("중대", "중요")
                  and re.search(r"군비|매칭|확보|확정|구두", o["problem"] + o["target_text"])]
        case("C5", "사실확인 검토: '확보했다'를 진술과 어긋난다고 짚음", bool(caught),
             caught[0]["problem"] if caught else f"짚지 못함(의견 {len(ops)}건: "
             + " / ".join(o["problem"][:60] for o in ops) + ")",
             model=ops[0]["model"] if ops else "", output=planted)

        # ── C6 가이드라인 AI 정리 ──
        f = _mock("01_")
        gl = call("post", f"/api/projects/{pid}/guidelines", params={"filename": f.name}, content=f.read_bytes())
        an = call("post", f"/api/guidelines/{gl['id']}/analyze", json={"use_ai": True, "provider": P})
        ok6 = (not an["fallback"]) and len(an["node_paths"]) == 12
        case("C6", "가이드라인 정리: AI 가 실제로 정리하고 목차 12개 유지", ok6,
             "통과" if ok6 else f"폴백={an['fallback']}({an.get('reason', '')}) · 목차 {len(an['node_paths'])}개",
             model=an.get("model", ""), note=f"자료 후보 {len(an['needs'])}건")

        # ── C7 초고 지시문 준수(마크다운) ──
        case("C7", "초고 지시문 준수: 제목 되풀이·마크다운을 쓰지 않음", not tidied,
             "통과" if not tidied else f"정리기가 {len(tidied)}곳 걷어 냄: " + " / ".join(tidied[:4]))
    except Exception as e:                       # 키 없음·네트워크 등 — 그 자리에서 멈추고 그대로 알린다
        case("ERR", "실행 중단", False, str(e)[:500])
    finally:
        db.DB_PATH = real_db
        if not keep_db:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)   # 임시 DB 에는 빌려 온 AI 키가 들어 있다

    return {"cases": cases, "passed": sum(c["ok"] for c in cases), "total": len(cases),
            "seconds": round(time.time() - t0, 1), "at": datetime.now().strftime("%Y-%m-%d %H:%M")}


def to_markdown(rep: dict) -> str:
    models = sorted({c.get("model") for c in rep["cases"] if c.get("model")})
    out = [f"# AI 품질 시험 — {rep['at']}", "",
           f"**{rep['passed']} / {rep['total']} 통과** · 모델: {', '.join(models) or '(없음)'} · {rep['seconds']}초", "",
           "| | 항목 | 결과 |", "|---|---|---|"]
    for c in rep["cases"]:
        out.append(f"| {c['id']} | {c['name']} | {'✅' if c['ok'] else '❌'} {c['detail']} |")
    out.append("")
    for c in rep["cases"]:
        if c.get("output"):
            out += [f"## {c['id']} {c['name']}", ""]
            if c.get("note"):
                out += [c["note"], ""]
            if c.get("findings"):
                out += ["근거 점검기: " + ", ".join(c["findings"]), ""]
            out += ["```", c["output"].strip(), "```", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="AI 품질 시험 묶음(실제 AI 를 부른다 — 요금이 든다)")
    ap.add_argument("--provider", help="openai|claude|gemini|compat (비우면 설정대로)")
    args = ap.parse_args(argv)
    rep = run(provider=args.provider)
    md = to_markdown(rep)
    outdir = BACKEND / "evals" / "results"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    path.write_text(md, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md.split("\n## ")[0])
    print(f"\n자세한 출력: {path}")
    return 0 if rep["passed"] == rep["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
