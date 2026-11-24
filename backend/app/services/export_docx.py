# -*- coding: utf-8 -*-
"""최종본 조립 · .docx 출력.

원칙: AI가 최종본을 다시 쓰지 않는다. 사용자가 반영한 본문(drafts.body)을
목차 순서대로 그대로 이어붙인다. 이 모듈은 '조립'만 한다.
한글(HWP)에서 열어 다듬을 수 있도록 .docx 로 저장하고 한글 글꼴을 지정한다.
"""
from __future__ import annotations
import io
import json
import re
from ..db import connect
from .numbering import evidence_numbers, sections_with_body
from .evidence import STATEMENT_KIND

# 비어 있거나 '+ 근거 추가'의 옛 자리표시('새 주장', '새 주장1')가 그대로인 주장
_PLACEHOLDER = re.compile(r"^(새 주장\d*)?$")


def _evidence_rows(c, pid):
    rows = c.execute("SELECT * FROM evidence WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    nos = evidence_numbers(c, pid)   # 본문의 '(근거: E-003)' 과 같은 번호
    out = []
    for e in rows:
        name = ""
        state = ""
        if e["resource_id"]:
            r = c.execute("SELECT name FROM resources WHERE id=?", (e["resource_id"],)).fetchone()
            a = c.execute("SELECT state FROM resource_analysis WHERE resource_id=?", (e["resource_id"],)).fetchone()
            name = r["name"] if r else ""
            state = a["state"] if a else ""
        out.append({"no": nos.get(e["id"], ""), "claim": e["claim"], "resource": name or "근거 없음",
                    "locator": e["locator"], "quote": e["quote"] if "quote" in e.keys() else "",
                    "status": e["status"], "confirmed": state == "사용자 확정"})
    return out


def _apply_font(style, font_name):
    from docx.oxml.ns import qn
    style.font.name = font_name
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        from docx.oxml import OxmlElement
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font_name)


def _set_korean_font(doc, font_name="맑은 고딕"):
    """본문뿐 아니라 제목 스타일에도 한글 글꼴을 지정한다.
    Normal 만 바꾸면 목차 제목이 기본 라틴 글꼴로 나가 한글이 어색해진다."""
    targets = ["Normal", "Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4"]
    for name in targets:
        try:
            _apply_font(doc.styles[name], font_name)
        except KeyError:
            continue      # 템플릿에 없는 스타일은 건너뛴다


# ────────────────────────── 보고전(한 쪽) 서식 ──────────────────────────
# 개조식 줄머리 → 들여쓰기 깊이. 초고(skills/draft_writing)가 ○ 와 - 를 쓰지만,
# 사람이 손으로 고치면서 □·· 도 섞이므로 실제로 쓰이는 것을 폭넓게 받는다.
_BULLETS = [
    ("□■▣▪", 0),
    ("○ㅇ◦●", 1),
    ("-–—·‧*▪", 2),
]


_DEFAULT_MARK = ["○", "-", "·", "·"]


def _bullet_level(line: str) -> tuple[int, str, str]:
    """줄머리를 보고 (깊이, 줄머리, 줄머리를 뗀 글자)를 돌려준다.

    줄머리가 없으면 앞의 공백 두 칸을 한 단계로 센다(초고가 그렇게 들여 쓴다).
    깊이를 잃으면 개조식이 그냥 문단 더미가 된다 — 보고전에서는 형식이 곧 내용이다.

    **줄머리는 사람이 쓴 것을 그대로 쓴다.** 깊이로 다시 만들어 붙였더니 ○ 로 쓴 줄이
    - 로 바뀌어 나왔다. 깊이는 들여쓰기에만 쓰고, 글자는 손대지 않는다
    (본문을 고쳐 쓰지 않는다는 원칙이 서식에도 그대로 적용된다).
    """
    raw = line.rstrip()
    stripped = raw.lstrip()
    indent = (len(raw) - len(stripped)) // 2
    for marks, lv in _BULLETS:
        if stripped[:1] in marks:
            return max(lv, indent), stripped[0], stripped[1:].lstrip()
    lv = min(indent, 3)
    return lv, _DEFAULT_MARK[lv], stripped


def _brief_docx(doc, proj, sections, dept, author):
    """한 쪽짜리 보고전. 계획서 서식(표지 제목 + 장별 heading)과 다른 물건이다.

    보고전의 값어치는 속도다. 표지도 목차 번호도 없고, 머리글 한 줄 + 제목 + 개조식 본문으로
    바로 시작한다. 여백을 좁혀 한 쪽에 담기게 한다.
    """
    from docx.shared import Pt, Mm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from datetime import date

    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Mm(15)
    sec.left_margin = sec.right_margin = Mm(18)
    normal = doc.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.35

    # 머리글: 부서 · 작성자 · 날짜 (오른쪽). 비어 있는 것은 넣지 않는다.
    head = " · ".join(x for x in (dept, author, date.today().strftime("%Y. %m. %d.")) if x)
    if head:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r = p.add_run(head)
        r.font.size = Pt(9.5)

    # 제목: 가운데, 굵게, 아래 선
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = t.add_run(proj["name"] or "제목 없음")
    tr.bold = True
    tr.font.size = Pt(17)
    t.paragraph_format.space_after = Pt(10)
    _bottom_border(t)

    for i, s in enumerate(sections):
        depth = max(s["depth"], 1)
        body = (s["body"] or "").strip()
        # 하위 항목을 거느린 자리('본문'·'결론' 같은 묶음)는 본문이 없는 것이 정상이다.
        # 거기에 '(본문 없음)'을 찍으면 한 쪽짜리 보고서가 빈칸 표시로 지저분해진다.
        has_children = i + 1 < len(sections) and sections[i + 1]["depth"] > s["depth"]
        # 항목 제목: 깊이에 따라 □ / ○ / -. 보고전에는 번호를 붙이지 않는다(행정 관습).
        mark = "□" if depth == 1 else ("○" if depth == 2 else "-")
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(12 * (depth - 1))
        p.paragraph_format.space_before = Pt(9 if depth == 1 else 4)
        r = p.add_run(f"{mark} {s['title']}")
        r.bold = depth <= 2
        r.font.size = Pt(12 if depth == 1 else 11)
        if not body:
            if has_children:
                continue
            e = doc.add_paragraph()
            e.paragraph_format.left_indent = Pt(12 * depth + 10)
            er = e.add_run("(본문 없음)")
            er.italic = True
            er.font.size = Pt(9.5)
            continue
        for line in body.split("\n"):
            if not line.strip():
                continue
            lv, lead, text = _bullet_level(line)
            bp = doc.add_paragraph()
            bp.paragraph_format.left_indent = Pt(12 * depth + 12 * lv + 10)
            bp.paragraph_format.first_line_indent = Pt(-10)   # 둘째 줄이 줄머리에 맞게
            bp.add_run(f"{lead} {text}")


def _bottom_border(p):
    """문단 아래 가로선. 보고전 제목 밑줄로 쓴다."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "666666")
    pbdr.append(bottom)
    p._p.get_or_add_pPr().append(pbdr)


def build_docx(pid, include_evidence=True) -> tuple[bytes, str]:
    """조립된 .docx 를 (bytes, 파일명) 으로 반환한다.

    계열에 따라 서식이 갈린다 — 계획서는 표지·장별 제목, 보고전은 한 쪽짜리 개조식.
    doc_type 이 초고 문체를 가르는 것과 같은 갈림이다(services/templates.family_of).
    """
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from .templates import family_of

    with connect() as c:
        proj = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not proj:
            raise ValueError("업무를 찾을 수 없습니다.")
        sections = sections_with_body(c, pid)
        ev = _evidence_rows(c, pid) if include_evidence else []
        dept = _setting(c, "author_dept")
        author = _setting(c, "author_name")

    doc = Document()
    _set_korean_font(doc)

    if family_of(proj["doc_type"]) == "보고전":
        _brief_docx(doc, proj, sections, dept, author)
        return _finish(doc, proj, ev, include_evidence)

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

    return _finish(doc, proj, ev, include_evidence)


def _setting(c, key: str) -> str:
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return (r["value"] if r else "") or ""


def _finish(doc, proj, ev, include_evidence) -> tuple[bytes, str]:
    """부록(근거표)을 붙이고 파일로 굽는다. 계획서·보고전이 함께 쓴다.

    부록은 **쪽을 넘겨** 붙인다 — 보고전의 본문 한 쪽을 근거표가 밀어내면
    '한 쪽짜리'라는 값어치가 사라진다.
    """
    if include_evidence and ev:
        doc.add_page_break()
        doc.add_heading("[부록] 근거표", level=1)
        # 번호 열이 있어야 본문의 '(근거: E-003)' 을 부록에서 찾아갈 수 있다.
        table = doc.add_table(rows=1, cols=5)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        for i, h in enumerate(["번호", "주장·판단", "근거자료", "위치·원문 인용", "상태"]):
            hdr[i].text = h
        for r in ev:
            cells = table.add_row().cells
            cells[0].text = r["no"] or ""
            cells[1].text = r["claim"] or ""
            cells[2].text = (r["resource"] or "") + (" ✔" if r["confirmed"] else "")
            # 원문 인용은 '이 주장이 원문의 어느 글에서 왔는가' — 심사자·감사자가 찾아갈 자리다.
            q = (r.get("quote") or "").strip()
            loc = (r["locator"] or "").strip()
            shown = f"“{q[:150]}{'…' if len(q) > 150 else ''}”" if q else ""
            cells[3].text = "\n".join(x for x in (loc if loc != q else "", shown) if x)
            cells[4].text = r["status"] or ""

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
        sections = sections_with_body(c, pid)
        opinions = [dict(r) for r in c.execute("SELECT * FROM review_opinions WHERE project_id=?", (pid,)).fetchall()]
        # 근거 경고
        changed = c.execute("SELECT COUNT(*) n FROM evidence WHERE project_id=? AND source_changed=1", (pid,)).fetchone()["n"]
        # 담당자 진술로만 뒷받침되는 근거. 내부 보고엔 충분해도 대외 제출에는 문서가 필요하다.
        stmt = c.execute(
            "SELECT COUNT(*) n FROM evidence e JOIN resources r ON e.resource_id=r.id "
            "WHERE e.project_id=? AND r.kind=?", (pid, STATEMENT_KIND)).fetchone()["n"]
        # 근거 점검기(규칙): 본문의 숫자·근거 번호를 근거 원문과 대조한 의견
        from .evidence_check import check_project
        ev_found = check_project(c, pid)
        # 항목 간 정합성(규칙): 같은 지표가 목차마다 다른 값으로 나오는 곳
        from .consistency import check_sections
        mismatched_values = check_sections(sections)
        # 2026-11-24 실제 업무(#6)에서 드러난 세 가지 — 부록이 사실과 다르게 읽히는 자리
        nos = evidence_numbers(c, pid)
        evs = [dict(r) for r in c.execute("SELECT * FROM evidence WHERE project_id=? ORDER BY id", (pid,))]
        # ① 주장이 비었거나 '+ 근거 추가'의 옛 자리표시('새 주장')가 그대로인 근거
        blank_claims = [nos.get(e["id"], "") for e in evs if _PLACEHOLDER.match((e["claim"] or "").strip())]
        # ② 요청과 다른 회신을 근거로 씀(분석이 '요청한 ○○은 이 자료에 없습니다'라고 한 자료)
        from ..skills.resource_analysis import asked_missing
        mismatched = []
        for e in evs:
            if not e["resource_id"]:
                continue
            a = c.execute("SELECT cautions FROM resource_analysis WHERE resource_id=?", (e["resource_id"],)).fetchone()
            try:
                miss = asked_missing(json.loads(a["cautions"])) if a else []
            except ValueError:
                miss = []
            if miss:
                r = c.execute("SELECT name FROM resources WHERE id=?", (e["resource_id"],)).fetchone()
                mismatched.append(f"{nos.get(e['id'], '')} {(r['name'] if r else '')[:40]} — 요청한 것 {len(miss)}가지 없음")
        # ④ 원문 인용이 자료 본문에 그대로 없는 근거(근거 고리 — 부록이 '원문'이라 말하는 글이 원문에 없다)
        from .quote import quote_state
        bad_quotes = []
        for e in evs:
            if e["resource_id"] and (e.get("quote") or "").strip():
                r = c.execute("SELECT text FROM resources WHERE id=?", (e["resource_id"],)).fetchone()
                if quote_state(e["quote"], r["text"] if r else "") == "불일치":
                    bad_quotes.append(f"{nos.get(e['id'], '')} {(e['claim'] or '')[:40]}")
        # ③ '회신옴'인데 받은 자료가 지워진 요청(요청 대장이 받지 않은 것을 받았다고 말한다)
        lost = [r["need"][:50] for r in c.execute(
            "SELECT need FROM data_requests WHERE project_id=? AND status='회신옴' AND received_resource_id IS NOT NULL "
            "AND received_resource_id NOT IN (SELECT id FROM resources)", (pid,))]

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
    if mismatched:
        items.append({"level": "중요", "label": "요청과 다른 회신을 근거로 씀",
                      "detail": mismatched + ["부록에는 요청 이름으로 보입니다 — 맞는 자료를 다시 받거나, 근거를 바꾸세요"]})
    if bad_quotes:
        items.append({"level": "중요", "label": "원문 인용이 자료 본문에 없는 근거",
                      "detail": bad_quotes + ["자료를 고쳤거나 인용을 잘못 옮겼습니다 — 근거표에서 인용을 원문대로"]})
    if blank_claims:
        items.append({"level": "중요", "label": "주장이 비어 있는 근거",
                      "detail": [f"{n or '(번호 없음)'} — 근거표에서 주장 칸을 채우세요(부록에 그대로 나갑니다)"
                                 for n in blank_claims]})
    if lost:
        items.append({"level": "참고", "label": "회신 자료가 지워진 자료요청",
                      "detail": [f"{x} — 상태는 '회신옴'이지만 받은 자료가 없습니다" for x in lost]})
    # 근거 점검기 — 종류별로 묶어 보인다. 막지는 않지만(사람이 판단) '중대·중요'는 준비 안 됨으로 센다.
    for kind in dict.fromkeys(f["kind"] for f in ev_found):
        group = [f for f in ev_found if f["kind"] == kind]
        items.append({"level": group[0]["level"], "label": f"근거 점검: {kind}",
                      "detail": [f"{f['section']} — {f['text']}" for f in group]})
    if mismatched_values:
        items.append({"level": "중요", "label": "같은 지표가 목차마다 다른 값으로 나옴",
                      "detail": [f["text"] for f in mismatched_values]
                      + ["낱말·연도·단위로 같은 지표라고 짐작한 것입니다 — 다른 것을 가리키면 그대로 두세요"]})
    if stmt:
        # 막지 않는다. 다만 보이게 한다 — 문서로 확인됐는지 판단하는 것은 사람의 몫이다.
        items.append({"level": "참고", "label": "담당자 진술로만 뒷받침되는 근거",
                      "detail": [f"{stmt}건 — 대외 제출 문서라면 문서 근거가 필요한지 확인하세요"]})

    # '참고'는 알려 주기만 하는 항목이다(진술 근거 등). 이것만 남았으면 준비된 것으로 본다 —
    # 보고전은 근거가 대부분 진술이라, 참고까지 막으면 점검이 늘 빨간불이 되어 무의미해진다.
    blocking = [x for x in items if x["level"] != "참고"]
    return {"ok": len(blocking) == 0, "sections": len(sections), "items": items}
