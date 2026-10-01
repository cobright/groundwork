# -*- coding: utf-8 -*-
"""문서 읽기 — .pdf / .hwpx / .hwp / .xlsx / .docx 를 **하나의 중간형식**으로 돌려준다.

왜 하나로 모으는가:
  가이드라인은 형식이 제각각으로 온다. 실제로 공모 한 건에 공고(.hwpx),
  서식(.hwp), 별도 가이드라인(.pdf)이 함께 왔다(2026-08-29 확인).
  부서 회신 자료는 여기에 엑셀(.xlsx)과 워드(.docx)가 더해진다.
  구조를 읽는 쪽(services/guideline.py)이 형식마다 갈라지면 규칙이 다섯 벌이 된다.
  그래서 여기서 **문단(para)과 표(table)의 순서 있는 목록**으로 통일한다.

중간형식(Block)
  i     문서 안 순번(0부터). 읽을 범위를 고를 때 이 번호를 쓴다.
  page  PDF 만 실제 쪽 번호. hwpx/hwp 는 0(쪽이라는 개념이 파일에 없다).
  kind  'para' | 'table'
  text  사람이 읽는 한 줄. 표는 격자를 '│'로 이은 요약.
  rows  표일 때만. 병합셀을 펼친 **직사각 격자**(services/guideline.py 가 이걸 쓴다).

표를 격자로 펴는 이유:
  배점표는 표다. 문단으로 읽으면 '배점 20'이 어느 지표 건지 사라진다.
  병합된 칸은 원래 칸의 글자를 그대로 채워 넣어 **행 하나가 스스로 완결**되게 한다.

의존성: pdf 는 pypdf, 엑셀은 openpyxl(둘 다 이미 들어 있다). 나머지는 표준 라이브러리.
"""
from __future__ import annotations

import datetime
import io
import re
import struct
import zipfile
import zlib
import defusedxml.ElementTree as ET   # 파싱은 안전한 쪽으로(XXE·XML 폭탄)
from html.parser import HTMLParser

P = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 한컴 기호 글꼴로 그린 글머리표는 사용자 영역 문자로 나온다(파서 오류가 아니다).
_PUA = re.compile("[" + chr(0xE000) + "-" + chr(0xF8FF) + "]")
# ezPDF 류가 만든 PDF 는 중점(중간점) 뒤에서 줄을 끊는다: '시‧\n군' -> '시‧군'
_MIDDOT_BREAK = re.compile("([‧·･])[ \t]*\n[ \t]*")
# 쪽 번호만 있는 줄
_PAGENO = re.compile(r"^-?\s*\d{1,4}\s*-?$")


class ReadError(Exception):
    """읽을 수 없는 파일. 사람이 읽는 말로 담는다(그대로 화면에 나간다)."""


def _clean(s: str) -> str:
    s = _PUA.sub("·", s or "")
    s = s.replace("　", " ").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def _block(i: int, page: int, kind: str, text: str, rows=None) -> dict:
    return {"i": i, "page": page, "kind": kind, "text": text, "rows": rows or []}


# ────────────────────────── PDF ──────────────────────────
def read_pdf(data: bytes) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ReadError("PDF 를 읽는 부품(pypdf)이 설치되어 있지 않습니다. "
                        "1_SETUP 을 다시 실행하거나, 한글에서 열어 본문을 붙여넣어 주세요.")
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        raise ReadError(f"PDF 를 열지 못했습니다({e}). 파일이 손상되었을 수 있습니다.")
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            raise ReadError("암호가 걸린 PDF 입니다. 암호를 푼 뒤 다시 올려주세요.")

    blocks, i = [], 0
    for pno, page in enumerate(reader.pages, 1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            raw = ""
        raw = _MIDDOT_BREAK.sub(r"\1", raw)
        for line in raw.splitlines():
            t = _clean(line)
            if not t or _PAGENO.match(t):
                continue
            blocks.append(_block(i, pno, "para", t))
            i += 1
    if not blocks:
        raise ReadError("PDF 에서 글자를 찾지 못했습니다. 스캔한 이미지 PDF 로 보입니다 — "
                        "한글에서 열어 본문을 붙여넣어 주세요.")
    return {"kind": "pdf", "pages": len(reader.pages), "blocks": blocks, "note": ""}


# ────────────────────────── HWPX ──────────────────────────
def _hwpx_cell_text(tc) -> str:
    """칸 안의 글. **문단 구분을 줄바꿈으로 남긴다.**

    공백으로 이어 붙이면 안 되는 이유: 한글은 문서 한 쪽을 통째로 1칸짜리 표
    (글상자)에 넣기도 한다. 실제로 어느 시·도 공고문은 본문 32문단이 전부 한 칸
    안에 있었고, 공백으로 이으니 문서 전체가 한 덩어리가 되어 목차가 하나도
    안 나왔다. 줄을 살려 두면 guideline.table_lines() 가 다시 글줄로 편다.
    """
    sub = tc.find(P + "subList")
    if sub is None:
        return ""
    out = []
    for p in sub.iter(P + "p"):
        line = _clean("".join(t.text or "" for t in p.iter(P + "t")))
        if line:
            out.append(line)
    return "\n".join(out)


def _hwpx_grid(tbl) -> list[list[str]]:
    """병합셀을 펼친 직사각 격자. 병합된 칸에는 원래 칸의 글자를 그대로 채운다."""
    rows = int(tbl.get("rowCnt") or 0)
    cols = int(tbl.get("colCnt") or 0)
    if rows <= 0 or cols <= 0:                     # 속성이 없으면 순서대로 채운다
        trs = tbl.findall(P + "tr")
        rows = len(trs)
        cols = max((len(tr.findall(P + "tc")) for tr in trs), default=0)
    if rows <= 0 or cols <= 0:
        return []
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    for tc in tbl.iter(P + "tc"):
        addr, span = tc.find(P + "cellAddr"), tc.find(P + "cellSpan")
        if addr is None:
            continue
        r, c = int(addr.get("rowAddr") or 0), int(addr.get("colAddr") or 0)
        rs = int(span.get("rowSpan") or 1) if span is not None else 1
        cs = int(span.get("colSpan") or 1) if span is not None else 1
        text = _hwpx_cell_text(tc)
        for dr in range(rs):
            for dc in range(cs):
                if r + dr < rows and c + dc < cols:
                    grid[r + dr][c + dc] = text
    return grid


def _hwpx_direct_text(p) -> str:
    """문단이 직접 가진 글자만. 표(tbl) 안으로는 내려가지 않는다.

    이걸 안 하면 표를 품은 문단이 '표 전체를 이어붙인 한 줄'로 한 번,
    개별 셀로 또 한 번 나와 같은 내용이 두 벌씩 쌓인다(실제 공고문에서 겪었다).
    """
    out = []

    def walk(el):
        for ch in el:
            if ch.tag == P + "tbl":
                continue
            if ch.tag == P + "t":
                out.append(ch.text or "")
            walk(ch)

    walk(p)
    return _clean("".join(out))


def read_hwpx(data: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ReadError("파일이 손상되었거나 HWPX 형식이 아닙니다.")
    blocks, i = [], 0
    with z:
        secs = sorted(n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n))
        if not secs:
            raise ReadError("HWPX 파일이 아닙니다(Contents/section0.xml 이 없습니다). "
                            ".hwp 라면 한글에서 .hwpx 로 다시 저장해 주세요.")

        def visit(el):
            nonlocal i
            for ch in el:
                if ch.tag == P + "tbl":
                    grid = _hwpx_grid(ch)
                    if grid:
                        # 한 줄 요약에는 줄바꿈을 넣지 않는다(칸 구분만 보이면 된다)
                        summary = " ／ ".join("│".join(c.replace("\n", " ") for c in r) for r in grid)
                        blocks.append(_block(i, 0, "table", _clean(summary)[:600], grid))
                        i += 1
                    continue                       # 표 안으로 다시 들어가지 않는다
                if ch.tag == P + "p":
                    t = _hwpx_direct_text(ch)
                    if t:
                        blocks.append(_block(i, 0, "para", t))
                        i += 1
                visit(ch)

        for s in secs:
            visit(ET.fromstring(z.read(s)))
    if not blocks:
        raise ReadError("HWPX 에서 글자를 찾지 못했습니다.")
    return {"kind": "hwpx", "pages": 0, "blocks": blocks, "note": ""}


# ────────────────────────── HWP 5.x (구형) ──────────────────────────
# OLE 복합문서(CFB)를 표준 라이브러리만으로 직접 읽는다. 자세한 배경은 docs/lessons.md 의 "문서·파일 읽기".
class _CFB:
    def __init__(self, data: bytes):
        if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise ReadError("한글 5.x(.hwp) 파일이 아닙니다.")
        self.d = data
        self.ssz = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mssz = 1 << struct.unpack_from("<H", data, 0x20)[0]
        nfat = struct.unpack_from("<I", data, 0x2C)[0]
        dir_start = struct.unpack_from("<I", data, 0x30)[0]
        self.cutoff = struct.unpack_from("<I", data, 0x38)[0]
        mini_start = struct.unpack_from("<I", data, 0x3C)[0]
        difat_start = struct.unpack_from("<I", data, 0x44)[0]
        ndifat = struct.unpack_from("<I", data, 0x48)[0]
        difat = list(struct.unpack_from("<109I", data, 0x4C))
        sec = difat_start
        for _ in range(ndifat):
            if sec >= 0xFFFFFFFA:
                break
            off, n = self._off(sec), self.ssz // 4 - 1
            difat += list(struct.unpack_from("<%dI" % n, data, off))
            sec = struct.unpack_from("<I", data, off + self.ssz - 4)[0]
        self.fat = []
        for s in difat[:nfat]:
            if s < 0xFFFFFFFA:
                self.fat += list(struct.unpack_from("<%dI" % (self.ssz // 4), data, self._off(s)))
        self.minifat = []
        s = mini_start
        while s < 0xFFFFFFFA:
            self.minifat += list(struct.unpack_from("<%dI" % (self.ssz // 4), data, self._off(s)))
            s = self.fat[s] if s < len(self.fat) else 0xFFFFFFFE
        self.dirs = []
        raw = self._chain(dir_start)
        for i in range(0, len(raw), 128):
            e = raw[i:i + 128]
            if len(e) < 128:
                break
            nlen = struct.unpack_from("<H", e, 64)[0]
            self.dirs.append({
                "name": e[:max(0, nlen - 2)].decode("utf-16-le", "replace"),
                "type": e[66],
                "start": struct.unpack_from("<I", e, 116)[0],
                "size": struct.unpack_from("<Q", e, 120)[0],
            })
        self.mini = self._chain(self.dirs[0]["start"])[:self.dirs[0]["size"]] if self.dirs else b""

    def _off(self, sec):
        return 512 + sec * self.ssz

    def _chain(self, sec):
        out, seen = bytearray(), set()
        while sec < 0xFFFFFFFA and sec not in seen:
            seen.add(sec)
            out += self.d[self._off(sec):self._off(sec) + self.ssz]
            sec = self.fat[sec] if sec < len(self.fat) else 0xFFFFFFFE
        return bytes(out)

    def _minichain(self, sec, size):
        out = bytearray()
        while sec < 0xFFFFFFFA and len(out) < size:
            o = sec * self.mssz
            out += self.mini[o:o + self.mssz]
            sec = self.minifat[sec] if sec < len(self.minifat) else 0xFFFFFFFE
        return bytes(out[:size])

    def read(self, name):
        for e in self.dirs:
            if e["name"] == name and e["type"] == 2:
                if e["size"] < self.cutoff:
                    return self._minichain(e["start"], e["size"])
                return self._chain(e["start"])[:e["size"]]
        return None


# 제어문자의 '폭'. 이걸 틀리면 뒤따르는 데이터 6워드가 글자로 새어 나온다.
# 탭(9)을 인라인에 넣지 않아 두 번 겪은 사고다 — 줄이지 말 것.
_EXT = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}   # 확장: 8워드
_INL = {4, 5, 6, 7, 8, 9, 19, 20}                          # 인라인: 8워드 (9 = 탭)


def _hwp_para_text(b: bytes) -> str:
    out, i, n = [], 0, len(b) // 2
    while i < n:
        c = struct.unpack_from("<H", b, i * 2)[0]
        if c in _EXT:
            out.append("\n")
            i += 8
        elif c in _INL:
            out.append("\t" if c == 9 else "")
            i += 8
        elif c < 32:
            if c in (10, 13):
                out.append("\n")
            i += 1
        else:
            out.append(chr(c))
            i += 1
    return "".join(out)


def _hwp_records(data: bytes):
    i = 0
    while i + 4 <= len(data):
        h = struct.unpack_from("<I", data, i)[0]
        i += 4
        tag, sz = h & 0x3FF, (h >> 20) & 0xFFF
        if sz == 0xFFF:
            sz = struct.unpack_from("<I", data, i)[0]
            i += 4
        yield tag, data[i:i + sz]
        i += sz


def read_hwp(data: bytes) -> dict:
    cfb = _CFB(data)
    fh = cfb.read("FileHeader") or b""
    compressed = bool(struct.unpack_from("<I", fh, 36)[0] & 1) if len(fh) >= 40 else True
    blocks, i, idx = [], 0, 0
    while True:
        raw = cfb.read("BodyText/Section%d" % idx) or cfb.read("Section%d" % idx)
        if raw is None:
            break
        if compressed:
            try:
                raw = zlib.decompress(raw, -15)
            except zlib.error:
                raise ReadError("한글 파일의 본문을 푸는 데 실패했습니다(암호가 걸린 문서일 수 있습니다).")

        def flush(parts):
            nonlocal i
            for line in "".join(parts).splitlines():
                t = _clean(line)
                if t and not _PAGENO.match(t):
                    blocks.append(_block(i, 0, "para", t))
                    i += 1

        cur = []
        for tag, body in _hwp_records(raw):
            if tag == 66:                    # PARA_HEADER — 문단이 바뀐다
                flush(cur)
                cur = []
            elif tag == 67:                  # PARA_TEXT
                cur.append(_hwp_para_text(body))
        flush(cur)
        idx += 1
    if not blocks:
        raise ReadError("한글 파일에서 글자를 찾지 못했습니다.")
    # 구형 .hwp 의 표는 아직 못 읽는다. 조용히 넘기지 않고 화면에 적어 준다.
    return {"kind": "hwp", "pages": 0, "blocks": blocks,
            "note": "구형 한글(.hwp)은 본문 글자만 읽습니다. 표 안의 내용은 빠집니다 — "
                    "표가 중요하면 한글에서 .hwpx 로 다시 저장해 올려주세요."}


# ────────────────────────── XLSX (엑셀) ──────────────────────────
_XL_MAXROW = 600          # 시트 하나에서 읽을 최대 행. 부서 회신은 대개 수십 행이다.


def _xl_cell(v) -> str:
    """엑셀 칸 하나를 사람이 읽는 글자로. 날짜와 정수를 원래 모양으로 되돌린다.

    openpyxl 은 날짜를 datetime 으로, 정수도 float(2431.0)로 준다. 그대로 이으면
    '2431.0'·'2024-01-01 00:00:00' 이 되어 담당자가 원본과 대조할 수 없다.
    """
    if v is None:
        return ""
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d") if (v.hour == 0 and v.minute == 0) else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, datetime.date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return _clean(str(v))


def _drop_empty_cols(grid: list[list[str]]) -> list[list[str]]:
    """통째로 빈 열을 버린다.

    엑셀은 A·B 열을 비워 두고 C 열부터 쓰는 일이 흔하다(실물에서 확인).
    그대로 두면 모든 줄이 ` │  │ 124` 로 시작해 사람도 AI 도 읽기 나쁘다.
    빈 열은 정보가 없으므로 위치와 무관하게 버린다.
    """
    if not grid:
        return grid
    keep = [i for i in range(len(grid[0])) if any(row[i] for row in grid)]
    if not keep or len(keep) == len(grid[0]):
        return grid
    return [[row[i] for i in keep] for row in grid]


def read_xlsx(data: bytes) -> dict:
    """엑셀 — 시트마다 쓰인 칸만 잘라 **격자(rows)** 로 돌려준다.

    부서 회신 자료의 상당수가 엑셀이고, 거기 담긴 것은 대개 연도별 수치다.
    문단으로 풀어 읽으면 '2,431' 이 어느 해 어느 항목 건지 사라지므로
    다른 형식의 표와 같은 격자로 만든다 — 행 하나가 스스로 완결되게(hwpx 와 같은 규칙).

    · 병합셀은 원래 칸의 글자를 덮인 칸마다 채워 넣는다.
    · 수식은 저장된 계산값(data_only)을 읽는다.
    · 숨긴 시트는 건너뛴다(대개 계산용이고, 담당자가 보낸 '자료'가 아니다).
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ReadError("엑셀을 읽는 부품(openpyxl)이 없습니다. 1_SETUP.bat 을 다시 실행해 주세요.")
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        raise ReadError("엑셀 파일을 여는 데 실패했습니다(암호가 걸렸거나 손상된 파일일 수 있습니다).")
    blocks, i, notes, hidden = [], 0, [], 0
    try:
        for ws in wb.worksheets:
            if ws.sheet_state != "visible":
                hidden += 1
                continue
            fill = {}
            for rng in ws.merged_cells.ranges:
                top = ws.cell(rng.min_row, rng.min_col).value
                for r in range(rng.min_row, rng.max_row + 1):
                    for cc in range(rng.min_col, rng.max_col + 1):
                        fill[(r, cc)] = top
            grid, cut = [], False
            for r, row in enumerate(ws.iter_rows(), start=1):
                if r > _XL_MAXROW:
                    cut = True
                    break
                line = [_xl_cell(fill[(r, c.column)] if (r, c.column) in fill else c.value) for c in row]
                while line and not line[-1]:
                    line.pop()
                grid.append(line)
            while grid and not any(grid[-1]):
                grid.pop()
            if not any(any(x) for x in grid):
                continue
            width = max(len(x) for x in grid)
            grid = _drop_empty_cols([x + [""] * (width - len(x)) for x in grid])
            blocks.append(_block(i, 0, "para", f"[시트] {ws.title}"))
            i += 1
            summary = " ／ ".join("│".join(grid_row) for grid_row in grid[:40])
            blocks.append(_block(i, 0, "table", _clean(summary)[:600], grid))
            i += 1
            if cut:
                notes.append(f"‘{ws.title}’ 시트는 {_XL_MAXROW}행까지만 읽었습니다.")
    finally:
        wb.close()
    if not blocks:
        raise ReadError("엑셀에서 내용을 찾지 못했습니다. 빈 파일이거나, 수식만 있고 계산 결과가 "
                        "저장되어 있지 않을 수 있습니다(엑셀에서 한 번 열었다가 저장한 뒤 올려주세요).")
    if hidden:
        notes.append(f"숨긴 시트 {hidden}개는 건너뛰었습니다.")
    return {"kind": "xlsx", "pages": 0, "blocks": blocks, "note": " ".join(notes)}


# ────────────────────────── HTML 표 (.xls 로 위장해서 오는 것) ──────────────────────────
# 행정 시스템에서 '엑셀 내려받기'를 누르면 확장자만 .xls 이고 **내용은 HTML 표**인 파일이
# 나오는 일이 흔하다(실물에서 확인, 2026-08-29). 진짜 엑셀이 아니므로 openpyxl 로는 못 열고,
# 확장자만 보고 "구형 엑셀이니 .xlsx 로 저장하라"고 안내하면 담당자는 엉뚱한 길로 간다.
# 표라는 점은 같으므로 같은 격자로 읽어 들인다.
class _TableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.paras = [], []      # 표들 / 표 밖의 글줄
        self._tbl = self._row = None
        self._cell = None                     # [글자조각, colspan, rowspan]
        self._buf = []
        self._skip = 0                        # style/script 안은 글이 아니다

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script"):
            self._skip += 1
            return
        if tag == "table":
            self._flush_para()
            self.tables.append([])
            self._tbl = self.tables[-1]
        elif tag == "tr" and self._tbl is not None:
            self._tbl.append([])
            self._row = self._tbl[-1]
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ["", _int(a.get("colspan"), 1), _int(a.get("rowspan"), 1)]
        elif tag == "br":
            self._text(" ")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip = max(0, self._skip - 1)
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr":
            self._row = None
        elif tag == "table":
            self._tbl = self._row = self._cell = None
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "li", "br"):
            self._flush_para()

    def handle_data(self, d):
        self._text(d)

    def _text(self, d):
        if self._skip:
            return
        if self._cell is not None:
            self._cell[0] += d
        elif self._tbl is None:
            self._buf.append(d)

    def _flush_para(self):
        t = _clean("".join(self._buf).replace("\n", " "))
        self._buf = []
        if t:
            self.paras.append(t)

    def close(self):
        super().close()
        self._flush_para()


def _int(v, default=1) -> int:
    try:
        return max(1, int(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _html_grid(rows) -> list[list[str]]:
    """colspan/rowspan 을 펼쳐 직사각 격자로. 병합 규칙은 hwpx·docx 와 같다."""
    grid, pend = [], {}                       # pend: 아래로 이어질 칸 {(행,열): 글자}
    for r, cells in enumerate(rows):
        line, col = [], 0
        for text, cs, rs in cells:
            while (r, col) in pend:           # 위에서 내려온 세로 병합 자리
                line.append(pend.pop((r, col)))
                col += 1
            t = _clean(text.replace("\n", " "))
            for _ in range(cs):
                line.append(t)
                for dr in range(1, rs):
                    pend[(r + dr, col)] = t
                col += 1
        while (r, col) in pend:
            line.append(pend.pop((r, col)))
            col += 1
        grid.append(line)
    if not grid:
        return []
    width = max(len(x) for x in grid)
    return _drop_empty_cols([x + [""] * (width - len(x)) for x in grid])


def read_html_table(data: bytes) -> dict:
    """HTML 로 된 표 파일(.xls·.html)을 읽는다."""
    text = _decode(data)
    p = _TableHTML()
    try:
        p.feed(text)
        p.close()
    except Exception:
        raise ReadError("표를 읽는 데 실패했습니다(파일이 손상되었을 수 있습니다).")
    blocks, i = [], 0
    for t in p.paras:
        if not _PAGENO.match(t):
            blocks.append(_block(i, 0, "para", t))
            i += 1
    for rows in p.tables:
        grid = _html_grid(rows)
        if grid and any(any(r) for r in grid):
            summary = " ／ ".join("│".join(c for c in r) for r in grid[:40])
            blocks.append(_block(i, 0, "table", _clean(summary)[:600], grid))
            i += 1
    if not blocks:
        raise ReadError("파일에서 표나 글자를 찾지 못했습니다.")
    return {"kind": "html표", "pages": 0, "blocks": blocks,
            "note": "확장자는 .xls 이지만 내용은 HTML 표인 파일이라 표로 읽었습니다"
                    "(행정 시스템의 ‘엑셀 내려받기’가 흔히 이렇게 만듭니다)."}


def _decode(data: bytes) -> str:
    """한글 웹 출력은 utf-8 과 cp949 가 섞여 온다. 선언을 먼저 보고, 없으면 차례로 시도."""
    head = data[:2048].lower()
    if b"euc-kr" in head or b"ks_c_5601" in head or b"cp949" in head:
        order = ("cp949", "utf-8")
    else:
        order = ("utf-8-sig", "cp949")
    for enc in order:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _looks_html(data: bytes) -> bool:
    head = data[:4096].lstrip()[:4096].lower()
    return head.startswith(b"<") and (b"<table" in data[:200000].lower() or head.startswith(b"<html")
                                      or head.startswith(b"<!doctype html"))


# ────────────────────────── DOCX (워드) ──────────────────────────
def _docx_text(el) -> str:
    """문단이 직접 가진 글자만. 표(tbl) 안으로는 내려가지 않는다(hwpx 와 같은 이유)."""
    out = []

    def walk(e):
        for ch in e:
            if ch.tag == W + "tbl":
                continue
            if ch.tag == W + "t":
                out.append(ch.text or "")
            elif ch.tag in (W + "tab", W + "br", W + "cr"):
                out.append(" ")
            walk(ch)

    walk(el)
    return _clean("".join(out))


def _docx_grid(tbl) -> list[list[str]]:
    """가로 병합(gridSpan)은 펼치고, 세로 병합(vMerge)은 윗 칸 글자를 물려받는다."""
    grid = []
    for tr in tbl.findall(W + "tr"):
        row = []
        for tc in tr.findall(W + "tc"):
            pr, span, carry = tc.find(W + "tcPr"), 1, False
            if pr is not None:
                gs = pr.find(W + "gridSpan")
                if gs is not None:
                    try:
                        span = max(1, int(gs.get(W + "val") or 1))
                    except ValueError:
                        span = 1
                vm = pr.find(W + "vMerge")
                if vm is not None and (vm.get(W + "val") or "continue") == "continue":
                    carry = True
            text = " ".join(t for t in (_docx_text(p) for p in tc.findall(W + "p")) if t)
            if carry and grid and len(grid[-1]) > len(row):
                text = grid[-1][len(row)]
            row += [text] * span
        grid.append(row)
    if not grid:
        return []
    width = max(len(r) for r in grid)
    return [r + [""] * (width - len(r)) for r in grid]


def read_docx(data: bytes) -> dict:
    """워드 — 문단과 표를 순서대로. 세부사업계획서가 .docx 로 오는 경우가 있다."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ReadError("파일이 손상되었거나 워드(.docx) 형식이 아닙니다.")
    with z:
        try:
            root = ET.fromstring(z.read("word/document.xml"))
        except KeyError:
            raise ReadError("워드 파일이 아닙니다(word/document.xml 이 없습니다). "
                            "구형 .doc 라면 워드에서 .docx 로 다시 저장해 주세요.")
    blocks, i = [], 0

    def visit(el):
        nonlocal i
        for ch in el:
            if ch.tag == W + "tbl":
                grid = _docx_grid(ch)
                if grid:
                    summary = " ／ ".join("│".join(c.replace("\n", " ") for c in r) for r in grid)
                    blocks.append(_block(i, 0, "table", _clean(summary)[:600], grid))
                    i += 1
                continue                           # 표 안으로 다시 들어가지 않는다
            if ch.tag == W + "p":
                t = _docx_text(ch)
                if t and not _PAGENO.match(t):
                    blocks.append(_block(i, 0, "para", t))
                    i += 1
                continue
            visit(ch)                              # 내용 컨트롤(sdt) 등으로 한 겹 싸인 경우

    visit(root)
    if not blocks:
        raise ReadError("워드 파일에서 글자를 찾지 못했습니다.")
    return {"kind": "docx", "pages": 0, "blocks": blocks, "note": ""}


# ────────────────────────── 입구 ──────────────────────────
def _zip_kind(data: bytes) -> str:
    """압축(PK)으로 시작하는 형식 가르기: xlsx / docx / hwpx."""
    try:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    except zipfile.BadZipFile:
        raise ReadError("파일이 손상되었습니다(압축을 풀 수 없습니다). 다시 내려받아 올려주세요.")
    if any(n.startswith("xl/") for n in names):
        return "xlsx"
    if "word/document.xml" in names:
        return "docx"
    return "hwpx"


def _cfb_kind(data: bytes) -> str:
    """OLE 복합문서는 한글(.hwp)·엑셀(.xls)·워드(.doc)가 시그니처를 함께 쓴다.
    안에 든 스트림 이름으로 갈라, 못 읽는 형식은 '왜'와 '어떻게 하면 되는지'를 말해 준다."""
    try:
        names = {d["name"] for d in _CFB(data).dirs}
    except Exception:
        return "hwp"
    if "Workbook" in names or "Book" in names:
        return "xls"
    if "WordDocument" in names:
        return "doc"
    return "hwp"


def to_text(doc: dict, max_chars: int = 60000) -> str:
    """읽은 문서를 자료 본문(resources.text)으로 쓸 글자로 편다.

    표는 격자를 그대로 살려 **한 행이 한 줄**이 되게 한다. 부서가 보내는 엑셀은
    '항목 × 연도' 표가 대부분이라, 칸을 뭉개면 '2,431' 이 어느 해 것인지 사라진다.
    담당자가 원본과 대조할 수 있어야 하고, 그래야 AI 분석도 지어내지 않는다.
    """
    out, n, cut = [], 0, False
    for b in doc.get("blocks", []):
        if b["kind"] == "table" and b.get("rows"):
            lines = []
            for row in b["rows"]:
                cells = [c.replace("\n", " ").strip() for c in row]
                while cells and not cells[-1]:      # 오른쪽 빈 칸은 버린다
                    cells.pop()
                if not cells:
                    continue
                # 한 줄이 전부 같은 글자면 가로로 병합된 안내줄이다 — 한 번만 적는다
                lines.append(cells[0] if len(set(cells)) == 1 and len(cells) > 1 else " │ ".join(cells))
            piece = "\n".join(ln for ln in lines if ln.replace("│", "").strip())
        else:
            piece = b.get("text", "")
        if not piece:
            continue
        if n + len(piece) > max_chars:
            cut = True
            break
        out.append(piece)
        n += len(piece) + 1
    if cut:
        out.append(f"...(자료가 길어 앞부분 {max_chars:,}자만 담았습니다. 원본 파일은 그대로 보관되어 있습니다.)")
    return "\n".join(out)


def read_document(data: bytes, filename: str = "") -> dict:
    """확장자가 아니라 **내용**으로 형식을 가른다(이름은 자주 틀린다)."""
    if not data:
        raise ReadError("빈 파일입니다. 내려받기가 끊겼는지 확인해 주세요.")
    if data[:5] == b"%PDF-":
        return read_pdf(data)
    # 확장자만 .xls 이고 내용은 HTML 표인 파일. 시그니처가 없으므로 내용으로 알아본다.
    if _looks_html(data):
        return read_html_table(data)
    if data[:2] == b"PK":
        kind = _zip_kind(data)
        if kind == "xlsx":
            return read_xlsx(data)
        if kind == "docx":
            return read_docx(data)
        return read_hwpx(data)
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        kind = _cfb_kind(data)
        if kind == "xls":
            raise ReadError("구형 엑셀(.xls)은 읽지 못합니다. 엑셀에서 열어 "
                            "‘다른 이름으로 저장 → Excel 통합 문서(.xlsx)’ 로 바꿔 올려주세요.")
        if kind == "doc":
            raise ReadError("구형 워드(.doc)는 읽지 못합니다. 워드에서 열어 "
                            "‘다른 이름으로 저장 → Word 문서(.docx)’ 로 바꿔 올려주세요.")
        return read_hwp(data)
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    raise ReadError(f"읽을 수 없는 형식입니다(.{ext}). "
                    "한글(.hwpx/.hwp)·엑셀(.xlsx)·워드(.docx)·PDF 를 올려주세요.")
