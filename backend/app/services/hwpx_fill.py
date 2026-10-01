# -*- coding: utf-8 -*-
"""HWPX 양식 채우기 — 양식의 구조는 그대로 두고 내용만 우리 최종본으로 바꾼다.

원칙(CLAUDE.md §1):
- AI가 최종본을 다시 쓰지 않는다. 사용자가 확정한 본문(drafts.body)을 옮겨 담기만 한다.
- 양식은 사용자의 것이다. 서식·표·글꼴을 우리가 새로 만들지 않고 양식 것을 복제해 쓴다.
- 우리가 모르는 것(실제 쪽수)은 지어내지 않고 비워 사람에게 넘긴다.

기술(원칙 4 — 추가 설치 곤란):
- 파이썬 표준 라이브러리만 쓴다(zipfile + xml.etree). 외부 휠 없음.

양식에서 읽어내는 것:
- 개조식 수준별 문단 서식 — 글머리 기호(□ ○ ― ※)로 판정한다.
  양식이 같은 수준에 서로 다른 paraPr 를 쓰는 경우가 실제로 있어(2_보고서 양식.hwpx 의 ※),
  서식 ID 를 기준으로 삼으면 안 된다.
- 들여쓰기는 문단 여백이 아니라 '텍스트 앞 공백'이다(행정문서의 관행). 공백 수까지 복제한다.
- 장 제목은 표(1행 3열)다. 장 수가 다르면 이 표를 복제·삭제한다.

주의:
- <hp:linesegarray> 는 줄바꿈 위치 캐시다. 글자 수가 바뀐 문단에 남겨두면 한글에서 깨진다.
  손댄 문단에서는 반드시 제거한다(한글이 열 때 다시 계산한다).
- 다시 압축할 때 mimetype 은 첫 항목이면서 무압축(STORED)이어야 한다. 원본의 항목 순서와
  압축 방식을 그대로 복제한다.
"""
from __future__ import annotations

import io
import shutil
import tempfile
import defusedxml.ElementTree as ET   # XML 은 모두 이쪽으로 — XXE·XML 폭탄을 막는다.
# 표준 xml.etree 는 **쓰지 않는다**. 생성은 _subelement(), 트리는 ET.parse() 로 되고,
# 네임스페이스 접두사 등록(register_namespace)은 아예 필요 없는 것으로 판명됐다 —
# 접두사가 hp:·hs: 에서 ns0:·ns1: 로 바뀐 파일을 한글이 그대로 열어 준다(2026-10-01 실물 확인).
# 접두사는 XML 에서 의미를 갖지 않으므로 표준대로 동작하는 것이다.
import zipfile
from copy import deepcopy
from datetime import date
from pathlib import Path

from ..db import connect
from .numbering import outline_rows

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
P = "{%s}" % HP
ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ"

# 글머리 기호 → 개조식 수준. 3수준은 양식마다 ― / - / – 로 다르다.
MARK_LEVEL = {"□": 1, "○": 2, "―": 3, "-": 3, "–": 3, "‐": 3, "※": 4}
MARKS = MARK_LEVEL                      # (이름 호환)
# 양식에 그 수준이 없을 때만 쓰는 기본값. 실제 기호·앞공백은 양식에서 읽어 온다.
LEVELS = {1: ("□", 1), 2: ("○", 2), 3: ("―", 3), 4: ("※", 5)}


class FormError(ValueError):
    """양식이 우리가 다룰 수 있는 모양이 아닐 때."""


# ────────────── XML 도우미 ──────────────
def _subelement(parent, tag):
    """xml.etree 의 SubElement 와 같은 일. 표준 모듈을 import 하지 않으려고 직접 둔다
    (defusedxml 은 읽기만 안전하게 하고 '쓰는' API 는 내주지 않는다)."""
    el = parent.makeelement(tag, {})
    parent.append(el)
    return el



def _text(p) -> str:
    return "".join(t.text or "" for t in p.iter(P + "t"))


def _has_table(p) -> bool:
    return p.find(f".//{P}tbl") is not None


def _strip_lineseg(p) -> None:
    for el in p.iter():
        for child in list(el):
            if child.tag == P + "linesegarray":
                el.remove(child)


def _set_text(p, text: str) -> None:
    """run 이 하나인 문단의 텍스트를 바꾼다(서식은 그대로)."""
    runs = p.findall(P + "run")
    if not runs:
        return
    t = runs[0].find(P + "t")
    if t is None:
        t = _subelement(runs[0], P + "t")
    for sub in list(t):
        t.remove(sub)
    t.text = text
    for extra in runs[1:]:
        p.remove(extra)
    _strip_lineseg(p)


# ────────────── 양식 읽기 ──────────────
class Template:
    """양식에서 뽑아낸 '틀'. 여기에 있는 것만 복제해 쓴다."""

    def __init__(self, root):
        self.root = root
        self.tops = root.findall(f"./{P}p")
        self.levels: dict[int, tuple] = {}       # 수준 → (문단 틀, 글머리 기호, 앞공백 수)
        self.chapter = None
        self.toc_item = None
        self.body_start = None
        self._scan()

    def _scan(self):
        for p in self.root.iter(P + "p"):
            if _has_table(p):
                continue
            full = _text(p)
            s = full.strip()
            if not s:
                continue
            lv = MARK_LEVEL.get(s[0])
            if lv and lv not in self.levels:
                # 기호와 들여쓰기(앞 공백 수)를 양식에서 그대로 읽는다.
                # 앞공백은 양식마다 다르다(어떤 양식은 ※ 가 5칸, 어떤 양식은 7칸).
                pad = len(full) - len(full.lstrip(" "))
                self.levels[lv] = (deepcopy(p), s[0], pad)
            if self.toc_item is None and p.find(f".//{P}tab") is not None and s[:1] in ROMAN:
                self.toc_item = deepcopy(p)

        first_chapter = None
        for i, p in enumerate(self.tops):
            if not _has_table(p):
                continue
            s = _text(p).strip()
            if self.body_start is None and s == "제 목":
                self.body_start = i
            if s[:1] in ROMAN and len(s) > 1:
                # 목차 페이지의 장 목록(여러 장이 한 셀에 든 표)은 제외
                if sum(1 for ch in s if ch in ROMAN) == 1 and first_chapter is None:
                    first_chapter = i
                    self.chapter = deepcopy(p)
        if self.body_start is None and first_chapter is not None:
            # '제 목' 장이 없는 양식(표지 다음 바로 본문)은 첫 장 표 직전까지가 머리말이다
            self.body_start = first_chapter - 1

        missing = [n for n, v in (("개조식 문단", self.levels.get(1)),
                                  ("장 제목 표", self.chapter),
                                  ("본문 시작(제 목)", self.body_start)) if v is None]
        if missing:
            raise FormError(
                "이 양식에서 " + ", ".join(missing) + " 을(를) 찾지 못했습니다. "
                "표준 보고서 양식(표지·목차·'제 목'·장 제목 표 구조)인지 확인해 주세요.")

    def level(self, lv: int):
        """(문단 틀, 글머리 기호, 앞공백). 양식에 없는 수준은 가까운 것으로 대체한다."""
        for cand in (lv, lv - 1, lv + 1, 1):
            if cand in self.levels:
                el, mark, pad = self.levels[cand]
                if cand != lv:      # 대체할 때는 기호·들여쓰기만 원래 수준의 기본값으로
                    mark, pad = LEVELS[lv]
                return el, mark, pad
        raise FormError("양식에 개조식 문단이 없습니다.")


# ────────────── 문단 만들기 ──────────────
def _make_line(tpl: Template, lv: int, content: str):
    el, mark, pad = tpl.level(lv)
    p = deepcopy(el)
    _strip_lineseg(p)
    runs = p.findall(P + "run")
    if len(runs) >= 2:
        # 기호와 본문의 글꼴이 다른 경우(□ 가 그렇다): 기호 run 과 본문 run 을 나눠 채운다
        first = runs[0].find(P + "t")
        if first is None:
            first = _subelement(runs[0], P + "t")
        first.text = f"{' ' * pad}{mark} "
        second = runs[1].find(P + "t")
        if second is None:
            second = _subelement(runs[1], P + "t")
        for sub in list(second):
            second.remove(sub)
        second.text = content
        for extra in runs[2:]:
            p.remove(extra)
    else:
        _set_text(p, f"{' ' * pad}{mark} {content}")
    return p


def _make_chapter(tpl: Template, roman: str, title: str, first: bool, page_break: bool):
    p = deepcopy(tpl.chapter)
    _strip_lineseg(p)
    if not first:
        # 페이지 번호 재시작(newNum)은 첫 장에만 남긴다
        for run in p.findall(P + "run"):
            for ctrl in run.findall(P + "ctrl"):
                if ctrl.find(P + "newNum") is not None:
                    run.remove(ctrl)
        p.set("pageBreak", "1" if page_break else "0")
    cells = p.findall(f".//{P}tc")
    if cells:
        for cell, value in ((cells[0], roman), (cells[-1], " " + title)):
            for q in cell.findall(f"{P}subList/{P}p"):
                _set_text(q, value)
    return p


def _make_toc_item(tpl: Template, roman: str, title: str):
    """목차 한 줄. 쪽번호는 비운다 — 서버는 실제 쪽수를 알 수 없다."""
    p = deepcopy(tpl.toc_item)
    _strip_lineseg(p)
    runs = p.findall(P + "run")
    t0 = runs[0].find(P + "t")
    if t0 is not None:
        t0.text = roman
    if len(runs) > 1:
        t = runs[1].find(P + "t")
        if t is not None:
            t.text = f". {title}"
            tab = t.find(P + "tab")
            if tab is not None:
                tab.tail = ""      # 점선·탭은 남기고 숫자는 비운다
    return p


# ────────────── 본문 해석 ──────────────
def parse_body(text: str) -> list[tuple[int, str]]:
    """워크벤치 본문을 (개조식 수준, 내용) 목록으로. 글머리 기호는 양식 것으로 다시 붙인다."""
    out = []
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        core = line.lstrip("□○ㅇ―-·•※* \t")
        if not core:
            continue
        if line.startswith(("※", "*")) or "[확인 필요" in line or "[추정" in line:
            lv = 4
        elif line.startswith("□"):
            lv = 1
        elif line.startswith(("○", "ㅇ")):
            lv = 2
        elif line.startswith(("-", "·", "•", "―")):
            lv = 3
        else:
            lv = 2
        out.append((lv, core))
    return out


def _gather(pid: int):
    """업무의 목차 트리 + 확정 본문. 장 = 최상위 목차."""
    with connect() as c:
        proj = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not proj:
            raise ValueError("업무를 찾을 수 없습니다.")
        rows = outline_rows(c, pid)
        bodies = {}
        for r in c.execute("SELECT node_uid, body FROM drafts WHERE project_id=?", (pid,)):
            bodies[r["node_uid"]] = r["body"] or ""
    tree = {}
    for r in rows:
        tree.setdefault(r["parent_uid"] if r["depth"] > 1 else None, []).append(r)
    return proj, tree, bodies


def inspect_form(form_bytes: bytes) -> dict:
    """이 양식을 우리가 채울 수 있는지 미리 살핀다(올릴 때 바로 알려주기 위해).

    내보내기 시점에야 실패를 알게 하지 않는다. 못 다루는 양식이면 왜 그런지 말한다.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(form_bytes)) as z:
            if "Contents/section0.xml" not in z.namelist():
                return {"supported": False, "reason": "HWPX 파일이 아닙니다(Contents/section0.xml 없음).",
                        "levels": [], "chapters": 0}
            raw = z.read("Contents/section0.xml")
            sections = sum(1 for n in z.namelist() if n.startswith("Contents/section"))
    except zipfile.BadZipFile:
        return {"supported": False, "reason": "파일이 손상되었거나 HWPX 형식이 아닙니다.",
                "levels": [], "chapters": 0}

    root = ET.fromstring(raw)
    try:
        tpl = Template(root)
    except FormError as e:
        return {"supported": False, "reason": str(e), "levels": [], "chapters": 0}

    chapters = sum(1 for p in tpl.tops
                   if _has_table(p) and _text(p).strip()[:1] in ROMAN
                   and sum(1 for ch in _text(p) if ch in ROMAN) == 1)
    reason = ""
    if sections > 1:
        reason = f"구역이 {sections}개인 양식입니다. 첫 구역(section0)만 채웁니다."
    return {"supported": True, "reason": reason,
            "levels": sorted(tpl.levels), "chapters": chapters,
            "marks": {lv: tpl.levels[lv][1] for lv in sorted(tpl.levels)}}


# ────────────── 본체 ──────────────
def fill_form(pid: int, form_bytes: bytes, org: str = "",
              page_break: bool = False) -> tuple[bytes, str]:
    """양식(bytes)에 업무 pid 의 최종본을 채워 (결과 bytes, 파일명) 으로 돌려준다."""
    proj, tree, bodies = _gather(pid)
    chapters = tree.get(None, [])
    if not chapters:
        raise ValueError("목차가 없습니다. 먼저 목차를 만드세요.")
    title = proj["name"] or "제목 없음"

    work = Path(tempfile.mkdtemp(prefix="hwpx_"))
    try:
        with zipfile.ZipFile(io.BytesIO(form_bytes)) as z:
            order = [(i.filename, i.compress_type) for i in z.infolist()]
            names = {i.filename for i in z.infolist()}
            if "Contents/section0.xml" not in names:
                raise FormError("HWPX 파일이 아닙니다(Contents/section0.xml 이 없습니다).")
            z.extractall(work)

        sec_path = work / "Contents" / "section0.xml"
        raw = sec_path.read_bytes()
        tree_xml = ET.parse(io.BytesIO(raw))      # defusedxml 이 ElementTree 를 돌려준다
        root = tree_xml.getroot()
        tpl = Template(root)

        # 1) 표지·본문 제목, 날짜, 기관명
        today = date.today()
        datestr = f"{today.year}. {today.month}. {today.day}."
        # 표지 제목: 양식마다 자리표시 문구가 다르므로 '첫 표의 첫 글줄'을 제목으로 본다.
        # (보고서 양식에서 첫 표는 언제나 제목 상자다)
        for first, rest in _title_cells(tpl):
            _set_text(first, title)
            for q in rest:          # 제목이 두 줄로 나뉜 양식이 있다(첫 줄만 바꾸면 옛 제목이 남는다)
                _set_text(q, "")
        for p in root.iter(P + "p"):
            if _has_table(p):
                continue          # 표를 담은 바깥 문단은 건드리지 않는다(셀 안 문단만 교체)
            s = _text(p).strip()
            if s in ("보고서 양식(제목)", "제 목"):
                _set_text(p, title)
            elif _is_placeholder_date(s):
                _set_text(p, datestr)
            elif s == "기관명" and org:
                # 자리표시가 분명할 때만 바꾼다. 부서명 등을 함부로 덮어쓰지 않는다.
                _set_text(p, org)

        # 2) 목차 페이지의 장 목록을 우리 장으로 교체(쪽번호는 비운다)
        if tpl.toc_item is not None:
            _rebuild_toc(root, tpl, chapters)

        # 3) 본문: '제 목' 표 다음을 모두 걷어내고 새로 쌓는다
        for p in tpl.tops[tpl.body_start + 1:]:
            root.remove(p)
        for i, ch in enumerate(chapters):
            roman = ROMAN[i] if i < len(ROMAN) else str(i + 1)
            root.append(_make_chapter(tpl, roman, ch["title"], first=(i == 0),
                                      page_break=page_break))
            for p in _chapter_body(tpl, ch, tree, bodies):
                root.append(p)

        sec_path.write_bytes(ET.tostring(root, encoding="UTF-8", xml_declaration=True))
        _update_preview(work, title, datestr, org, chapters)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, method in order:            # mimetype 이 첫 항목·STORED 로 유지된다
                z.write(work / name, name, compress_type=method)
        safe = "".join(ch for ch in title if ch not in '\\/:*?"<>|').strip()[:40] or "보고서"
        return buf.getvalue(), f"{safe}.hwpx"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _title_cells(tpl: Template):
    """제목 상자: (첫 글줄, 같은 칸의 나머지 글줄들) 목록.
    표지(첫 표)와, 있다면 본문 머리의 '제 목' 표를 대상으로 한다."""
    out = []
    seen = 0
    for p in tpl.tops:
        if not _has_table(p):
            continue
        seen += 1
        if seen > 1 and _text(p).strip() != "제 목":
            continue
        for tc in p.findall(f".//{P}tc"):
            filled = [q for q in tc.findall(f"{P}subList/{P}p") if _text(q).strip()]
            if filled:
                out.append((filled[0], filled[1:]))
                break
        if seen > 1:
            break
    return out


def _is_placeholder_date(s: str) -> bool:
    parts = s.replace(" ", "").rstrip(".").split(".")
    return len(parts) == 3 and all(x.isdigit() for x in parts)


def _chapter_body(tpl: Template, ch, tree, bodies):
    """한 장의 내용: 하위 목차는 □, 본문 줄은 ○/―/※."""
    subs = tree.get(ch["uid"], [])
    if subs:
        for s in subs:
            yield _make_line(tpl, 1, s["title"])
            lines = parse_body(bodies.get(s["uid"], ""))
            if not lines:
                yield _make_line(tpl, 2, "(본문 없음)")
            for lv, txt in lines:
                yield _make_line(tpl, max(lv, 2), txt)
    else:
        lines = parse_body(bodies.get(ch["uid"], ""))
        if not lines:
            yield _make_line(tpl, 1, "(본문 없음)")
        for lv, txt in lines:
            yield _make_line(tpl, lv, txt)


def _rebuild_toc(root, tpl: Template, chapters):
    """목차 페이지의 장 목록을 우리 장으로 갈아끼운다.

    양식의 목차에는 장(로마숫자) 아래 하위 항목이 딸려 있는 경우가 있다. 그것은 양식이
    예시로 넣어둔 옛 목차이므로 함께 걷어낸다. 반면 마지막 장 뒤에 오는 [붙 임]·[참 고]·
    별지 안내는 우리 문서와 무관한 양식 고유의 안내이므로 그대로 둔다.
    """
    for sub in root.iter(P + "subList"):
        kids = list(sub)
        tabbed = [q for q in sub.findall(P + "p") if q.find(f".//{P}tab") is not None]
        romans = [q for q in tabbed if _text(q).strip()[:1] in ROMAN]
        if not romans:
            continue
        # [붙 임]·[참 고]·별지 같은 '꼬리 안내'가 시작되는 지점부터는 손대지 않는다.
        cutoff = len(kids)
        for i, q in enumerate(kids):
            t = _text(q).strip()
            if t[:1] in ("[", "•", "※", "◦", "○"):
                cutoff = i
                break
        stale = [q for q in tabbed
                 if q not in romans and kids.index(q) < cutoff]  # 옛 목차의 하위 항목
        anchor = kids.index(romans[0])
        for q in romans + stale:
            sub.remove(q)
        for i, ch in enumerate(reversed(chapters)):
            n = len(chapters) - i - 1
            roman = ROMAN[n] if n < len(ROMAN) else str(n + 1)
            sub.insert(anchor, _make_toc_item(tpl, roman, ch["title"]))
        return


def _update_preview(work: Path, title, datestr, org, chapters):
    """탐색기 미리보기가 옛 내용을 보여주지 않도록 갱신(한글이 열면 다시 만든다)."""
    prv = work / "Preview" / "PrvText.txt"
    if not prv.exists():
        return
    lines = [title, "", datestr, org, ""]
    lines += [f"{ROMAN[i] if i < len(ROMAN) else i + 1}. {ch['title']}"
              for i, ch in enumerate(chapters)]
    prv.write_text("\n".join(lines), encoding="utf-8")
