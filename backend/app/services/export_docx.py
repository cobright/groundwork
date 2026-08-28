# -*- coding: utf-8 -*-
"""최종본 조립 · .docx 출력.

원칙: AI가 최종본을 다시 쓰지 않는다. 사용자가 반영한 본문(drafts.body)을
목차 순서대로 그대로 이어붙인다. 이 모듈은 '조립'만 한다.
한글(HWP)에서 열어 다듬을 수 있도록 .docx 로 저장하고 한글 글꼴을 지정한다.
"""
from __future__ import annotations
import io
from ..db import connect


def _ordered_sections(c, pid):
    nodes = c.execute("SELECT uid,parent_uid,sort,title FROM outline_nodes WHERE project_id=? ORDER BY sort", (pid,)).fetchall()
    children = {}
    for n in nodes:
        children.setdefault(n["parent_uid"], []).append(n)
    for a in children.values():
        a.sort(key=lambda x: x["sort"])
    out = []
    def walk(parent, depth, prefix):
        for i, n in enumerate(children.get(parent, [])):
            num = f"{prefix}{i+1}"
            d = c.execute("SELECT body FROM drafts WHERE project_id=? AND node_uid=?", (pid, n["uid"])).fetchone()
            out.append({"uid": n["uid"], "number": num, "title": n["title"],
                        "depth": depth, "body": (d["body"] if d else "")})
            walk(n["uid"], depth + 1, num + ".")
    walk(None, 1, "")
    return out


def _evidence_rows(c, pid):
    rows = c.execute("SELECT * FROM evidence WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    out = []
    for e in rows:
        name = ""
        state = ""
        if e["resource_id"]:
            r = c.execute("SELECT name FROM resources WHERE id=?", (e["resource_id"],)).fetchone()
            a = c.execute("SELECT state FROM resource_analysis WHERE resource_id=?", (e["resource_id"],)).fetchone()
            name = r["name"] if r else ""
            state = a["state"] if a else ""
        out.append({"claim": e["claim"], "resource": name or "근거 없음", "locator": e["locator"],
                    "status": e["status"], "confirmed": state == "사용자 확정"})
    return out


def _set_korean_font(doc, font_name="맑은 고딕"):
    from docx.oxml.ns import qn
    style = doc.styles["Normal"]
    style.font.name = font_name
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        from docx.oxml import OxmlElement
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font_name)


def build_docx(pid, include_evidence=True) -> tuple[bytes, str]:
    """조립된 .docx 를 (bytes, 파일명) 으로 반환한다."""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    with connect() as c:
        proj = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not proj:
            raise ValueError("업무를 찾을 수 없습니다.")
        sections = _ordered_sections(c, pid)
        ev = _evidence_rows(c, pid) if include_evidence else []

    doc = Document()
    _set_korean_font(doc)

    # 표지 성격의 제목
    title = doc.add_heading(proj["name"] or "제목 없음", level=0)
    if proj["doc_type"]:
        sub = doc.add_paragraph(proj["doc_type"])
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in sub.runs:
            run.font.size = Pt(11)
    doc.add_paragraph("")

    # 본문: 반영된 body 를 그대로
    for s in sections:
        lvl = min(max(s["depth"], 1), 4)
        doc.add_heading(f"{s['number']} {s['title']}", level=lvl)
        body = (s["body"] or "").strip()
        if not body:
            p = doc.add_paragraph("(본문 없음)")
            for run in p.runs:
                run.italic = True
            continue
        for para in body.split("\n"):
            para = para.rstrip()
            if para.strip() == "":
                continue
            doc.add_paragraph(para)

    # 부록: 근거표
    if include_evidence and ev:
        doc.add_page_break()
        doc.add_heading("[부록] 근거표", level=1)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        for i, h in enumerate(["주장·판단", "근거자료", "위치", "상태"]):
            hdr[i].text = h
        for r in ev:
            cells = table.add_row().cells
            cells[0].text = r["claim"] or ""
            cells[1].text = (r["resource"] or "") + (" ✔" if r["confirmed"] else "")
            cells[2].text = r["locator"] or ""
            cells[3].text = r["status"] or ""

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    safe = "".join(ch for ch in (proj["name"] or "최종본") if ch not in '\\/:*?"<>|').strip()[:40] or "최종본"
    return buf.getvalue(), f"{safe}.docx"


def final_check(pid) -> dict:
    """내보내기 전 위험 점검. 막지 않고 사람이 확인하도록 목록만 돌려준다."""
    with connect() as c:
        proj = c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone()
        if not proj:
            raise ValueError("업무를 찾을 수 없습니다.")
        sections = _ordered_sections(c, pid)
        opinions = [dict(r) for r in c.execute("SELECT * FROM review_opinions WHERE project_id=?", (pid,)).fetchall()]
        # 근거 경고
        changed = c.execute("SELECT COUNT(*) n FROM evidence WHERE project_id=? AND source_changed=1", (pid,)).fetchone()["n"]

    empty = [f"{s['number']} {s['title']}" for s in sections if not (s["body"] or "").strip()]
    flagged = [f"{s['number']} {s['title']}" for s in sections
               if "[확인 필요" in (s["body"] or "") or "[추정" in (s["body"] or "")]
    unresolved = [o for o in opinions if o["status"] in ("미처리", "확인중")]
    crit_unresolved = [o for o in unresolved if o["severity"] in ("중대", "중요")]
    dropped_no_reason = [o for o in opinions
                         if o["status"] in ("반영안함", "보류") and o["severity"] in ("중대", "중요")
                         and not (o["user_note"] or "").strip()]

    items = []
    if empty:
        items.append({"level": "중요", "label": "본문이 없는 목차", "detail": empty})
    if flagged:
        items.append({"level": "중요", "label": "[확인 필요]·[추정] 표시가 남은 목차", "detail": flagged})
    if crit_unresolved:
        items.append({"level": "중대", "label": "미해결(중대·중요) 검토의견",
                      "detail": [f"[{o['kind']}] {o['problem'][:40]}" for o in crit_unresolved]})
    if dropped_no_reason:
        items.append({"level": "중대", "label": "중대·중요 의견을 사유 없이 '반영안함/보류'",
                      "detail": [f"[{o['kind']}] {o['problem'][:40]}" for o in dropped_no_reason]})
    if changed:
        items.append({"level": "중요", "label": "근거 자료가 변경된 근거 항목", "detail": [f"{changed}건 — 근거표에서 확인 필요"]})

    return {"ok": len(items) == 0, "sections": len(sections), "items": items}
