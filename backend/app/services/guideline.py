# -*- coding: utf-8 -*-
"""가이드라인 구조 인식 — **규칙만으로** 목차·집필카드·자료후보·배점표를 뽑는다.

왜 규칙이 먼저인가:
  공모 가이드라인은 이미 "무엇을 어느 항목에 쓰고, 어떤 자료가 필요한지"를
  본문에 적어 놓았다. AI가 상상할 것이 아니라 **읽어 낼 것**이다(원칙 2).
  그래서 여기서 최대한 뽑고, LLM(skills/guideline_analysis.py)은
  '이 각주가 자료 목록인가 설명인가', '요청 문구로 다듬기'만 맡는다.
  그 덕에 44쪽짜리를 통째로 LLM에 넣지 않아도 되고, 키가 없어도 목차는 나온다.

문서마다 표시가 다르다 (2026-08-29 실물 두 건에서 확인):
  가이드라인 PDF : 제N절 / N. / 원문자   + '주요내용' '방법(예시)' + '*' 각주
  공모 공고 HWPX : 로마숫자 / N. / 가.    + '※' 지시문 + 빈 표
  그래서 계층 표지를 **후보군**으로 두고, 그 문서에 실제로 나온 것만 골라
  고정 우선순위로 깊이를 매긴다. 규칙 하나로 고정하면 다음 문서에서 반드시 깨진다.

빈 표가 곧 자료 요구다:
  '읍·면 │ 전체 개소수 │ 가맹점수(가맹율)' 짜리 빈 표는
  "읍·면별 가맹점 수 자료를 구해 오라"는 뜻이다. 단위·구분까지 들어 있어
  문장으로 쓰인 요구보다 오히려 정확하다. 표 머리글을 자료 후보로 삼는다.
"""
from __future__ import annotations

import re

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
HANGUL_ORD = "가나다라마바사아자차카타파하"

# 계층 표지 후보. rank 가 작을수록 바깥(상위) 계층이다.
# 실제로 문서에 나온 종류만 골라 쓰므로, 없는 단계는 그냥 건너뛴다.
MARKERS: list[tuple[str, int, "re.Pattern"]] = [
    ("장",     0, re.compile(r"^제\s*(\d+)\s*장\s+(.+)$")),
    ("절",     1, re.compile(r"^제\s*(\d+)\s*절\s+(.+)$")),
    ("로마",   2, re.compile(rf"^([{ROMAN}])\s*[.)]\s*(.+)$")),
    ("아라비아", 3, re.compile(r"^(\d{1,2})\s*[.)]\s+(.+)$")),
    ("가나다",  4, re.compile(rf"^([{HANGUL_ORD}])\s*[.)]\s+(.+)$")),
    ("원문자",  5, re.compile(rf"^([{CIRCLED}])\s*(.+)$")),
]

# 지시문 표지 — "이 항목에 무엇을 쓰라"는 안내.
RE_INSTR = re.compile(r"^\s*(※|주요내용|방법|작성\s*방법|유의사항|▪|■|[◦○∘・·])\s*")
RE_EXAMPLE = re.compile(r"^\(\s*예시\s*\)\s*")
# 각주 — 자료 목록이 여기 자주 들어 있다(전부는 아니다. 판정은 LLM).
RE_NOTE = re.compile(r"^\s*\*+\s*(.+)$")
# 빈 본문 자리 표시(글머리표만 있는 줄)와, 앞줄에 딸린 꼬리표('(예시)' 처럼)
RE_EMPTY_BULLET = re.compile(r"^[◦○∘・·ㅇo\-–—□▪▶●\s]{0,4}$")
RE_TAG_ONLY = re.compile(r"^\(?\s*(예시|계속|이어짐)\s*\)?$")
# 지시문 본문 앞에 남는 글머리표
RE_LEAD_BULLET = re.compile(r"^[∘◦○・·\-–—▪●\s]+")
# 제목처럼 보이지 않는 잡음(쪽머리·붙임 표지 등)
RE_NOISE = re.compile(r"^(붙임|별첨|참고)\s*\d*\s*$")

# 분량 규정: 'A4 30page 이내', '30쪽 이내', '1페이지 분량'
RE_LENGTH = re.compile(r"(?:A4\s*)?(\d{1,3})\s*(?:page|페이지|쪽|p)\s*(이내|내외|분량)?")
# 날짜. 공고는 '‘25. 9. 29.(월) ~ 10. 13.(월)' 처럼 **뒤쪽 날짜에 연도를 생략**한다.
# 마감일은 그 생략된 쪽이므로, 앞에 나온 연도를 물려받아 읽어야 한다.
RE_DATE = re.compile(
    r"[‘']?(\d{2,4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?"      # 연.월.일
    r"|(?<![\d.])(\d{1,2})\s*\.\s*(\d{1,2})\s*\.(?!\d)"            # 월.일 (연도 생략)
)


def dates_in(text: str) -> list[str]:
    """글 한 줄에서 날짜를 순서대로 뽑는다(연도 생략분은 앞 연도를 물려받는다)."""
    out, year = [], None
    for m in RE_DATE.finditer(text or ""):
        if m.group(1):
            y = int(m.group(1))
            y = y if y >= 100 else 2000 + y
            mo, d = int(m.group(2)), int(m.group(3))
            year = y
        else:
            if year is None:
                continue
            y, mo, d = year, int(m.group(4)), int(m.group(5))
        if 2020 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
            out.append(f"{y:04d}-{mo:02d}-{d:02d}")
    return out

# 배점표를 알아보는 말
SCORE_HEAD = ("배점", "점수", "평가")
SCORE_ITEM = ("지표", "항목", "구분", "평가")
# 배점표 항목명에 붙는 배점 괄호: '소멸 위험도 (10)' -> '소멸 위험도'
RE_POINT_PAREN = re.compile(r"\s*\(\s*(?:최대\s*)?\d+(?:\.\d+)?\s*\)\s*$")


def score_label(item: str) -> str:
    """병합셀을 편 탓에 '공통 배점 (80) · 소멸 위험도 (10)' 처럼 뭉쳐 나온다.
    짝짓기에는 **가장 구체적인 마디**만 쓴다(앞의 큰 묶음은 유사도를 희석시킨다)."""
    last = (item or "").split(" · ")[-1].strip()
    return RE_POINT_PAREN.sub("", last).strip() or item


def flat(s: str) -> str:
    """표 칸의 글을 한 줄 이름으로 눕힌다.

    doc_read 는 칸 안 문단을 줄바꿈으로 남긴다(문서 한 쪽이 통째로 한 칸에 들어가는
    경우가 있어서다). 그 줄바꿈이 배점표의 지표명이나 표 머리글에 그대로 새어 나오면
    ‘성과
도출’ 처럼 깨져 보이고 유사도 짝짓기도 흐트러진다.
    """
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def _is_noise(t: str) -> bool:
    return (bool(RE_NOISE.match(t)) or RE_EMPTY_BULLET.match(t) is not None
            or RE_TAG_ONLY.match(t) is not None)


def table_lines(rows: list[list[str]]) -> list[str] | None:
    """표가 **표가 아닌** 경우 그 글줄을 돌려준다(아니면 None).

    한글 서식은 제목 띠와 '※ 이렇게 쓰시오' 안내를 흔히 **1칸짜리 표(글상자)**로
    그린다. 실제 공모 공고에서 'Ⅰ. 사업 개요'도 '※ 최근 인구증감률…'도 전부
    1칸 표였다. 이걸 표로 다루면 목차도 집필카드도 통째로 사라진다.
    칸이 한 종류뿐이거나 한 줄(한 열)짜리면 글상자로 본다.
    """
    vals = list(dict.fromkeys(c.strip() for r in rows for c in r if c.strip()))
    ncols = max((len(r) for r in rows), default=0)
    if not vals:
        return []
    if len(vals) == 1 or ncols <= 1:
        # 칸 안에 여러 문단이 들어 있으면(doc_read 가 줄바꿈으로 남긴다) 다시 편다.
        out = []
        for v in vals:
            out += [x.strip() for x in v.split("\n") if x.strip()]
        return out
    return None


def match_marker(text: str):
    """줄이 계층 표지로 시작하면 (종류, rank, 제목)을 돌려준다."""
    for name, rank, rx in MARKERS:
        m = rx.match(text)
        if m:
            title = m.group(2).strip()
            # 한 글자짜리·너무 긴 것은 제목이 아니다(본문 문장이 우연히 걸린 경우)
            if 1 < len(title) <= 60:
                return name, rank, title
    return None


# ────────────────────────── 구간 추정 ──────────────────────────
# '어디부터 어디까지가 목차·작성방법 부분인가'. 자동은 **기본값일 뿐**이고
# 사람이 화면에서 고친다. 조용히 틀린 구간을 잡는 것이 가장 나쁘다.
RANGE_HINTS = ("목차", "작성 방법", "작성방법", "작성 요령", "작성요령",
               "신청양식", "예비계획서", "사업계획서", "계획서 작성", "서식")


def guess_range(blocks: list[dict]) -> dict:
    """목차·작성방법으로 보이는 구간을 추정한다(없으면 문서 전체)."""
    start = None
    for b in blocks:
        t = b["text"]
        if len(t) <= 40 and any(h in t for h in RANGE_HINTS) and match_marker(t) is None:
            if any(k in t for k in ("목차", "작성", "양식", "계획서")):
                start = b["i"]
                break
    if start is None:
        return {"start": blocks[0]["i"], "end": blocks[-1]["i"], "guessed": False}
    # 시작 이후로 계층 표지가 가장 촘촘한 데까지를 끝으로 본다 = 문서 끝
    return {"start": start, "end": blocks[-1]["i"], "guessed": True}


# ────────────────────────── 목차 · 카드 · 자료후보 ──────────────────────────
def parse_outline(blocks: list[dict], start: int | None = None, end: int | None = None) -> dict:
    """구간에서 목차 항목을 뽑고, 각 항목에 딸린 지시문·자료후보를 붙인다."""
    lo = blocks[0]["i"] if start is None else start
    hi = blocks[-1]["i"] if end is None else end
    span = [b for b in blocks if lo <= b["i"] <= hi]

    # ① 글줄과 '진짜 표'로 가른다. 1칸짜리 표(글상자)는 글줄로 편다.
    lines: list[dict] = []
    for b in span:
        if b["kind"] == "table":
            plain = table_lines(b["rows"])          # 표가 아니라 글상자면 글줄 목록
            if plain is None:
                lines.append({"text": b["text"], "block": b["i"], "page": b["page"],
                              "rows": b["rows"]})
                continue
            for t in plain:
                lines.append({"text": t, "block": b["i"], "page": b["page"], "rows": None})
            continue
        lines.append({"text": b["text"], "block": b["i"], "page": b["page"], "rows": None})

    # ② 이 문서가 실제로 쓴 계층 표지만 골라 깊이를 매긴다.
    used = {}
    for ln in lines:
        if ln["rows"] is None:
            hit = match_marker(ln["text"])
            if hit:
                used[hit[0]] = hit[1]
    depth_of = {rank: i + 1 for i, rank in enumerate(sorted(used.values()))}

    items: list[dict] = []
    cur = None
    for ln in lines:
        t, blk, pg = ln["text"], ln["block"], ln["page"]
        if ln["rows"] is not None:                 # 진짜 표 = 채워 와야 할 자료 명세
            if cur is not None:
                head = [c for c in ln["rows"][0] if c.strip()]
                if len(head) >= 2:
                    cur["needs"].append({"text": flat(" · ".join(dict.fromkeys(flat(h) for h in head)))[:200],
                                         "source": "표", "block": blk, "page": pg})
            continue
        if _is_noise(t):
            continue
        hit = match_marker(t)
        if hit:
            name, rank, title = hit
            cur = {"title": title, "level": depth_of.get(rank, 1),
                   "block": blk, "page": pg, "marker": name,
                   "instr": [], "method": [], "needs": []}
            items.append(cur)
            continue
        if cur is None:
            continue
        note = RE_NOTE.match(t)
        if note:
            cur["needs"].append({"text": note.group(1).strip()[:300],
                                 "source": "각주", "block": blk, "page": pg})
            continue
        if RE_INSTR.match(t):
            body = RE_EXAMPLE.sub("", RE_INSTR.sub("", t).strip()).strip()
            body = RE_LEAD_BULLET.sub("", body).strip()
            if body:
                (cur["method"] if t.lstrip().startswith("방법") else cur["instr"]).append(body)
            continue
        # 표지 없는 이어지는 줄은 직전 통에 붙인다(각주·지시문이 여러 줄로 끊기는 경우)
        if cur["needs"] and cur["needs"][-1]["source"] == "각주" and t.startswith(("(", "-", "·")):
            cur["needs"][-1]["text"] = (cur["needs"][-1]["text"] + " " + t)[:300]
        elif cur["instr"]:
            cur["instr"][-1] = (cur["instr"][-1] + " " + t)[:600]

    # 지시문 안에도 자료 나열이 있다("※ 최근 인구증감률, 고령화비율 등 인구 현황").
    # 쉼표로 여러 개를 늘어놓은 줄이 그렇다. 판정은 LLM 이 하고 여기선 후보로만 올린다.
    for it in items:
        for line in it["instr"]:
            if line.count(",") >= 2 and len(line) <= 300:
                it["needs"].append({"text": line, "source": "지시문",
                                    "block": it["block"], "page": it["page"]})
        seen, uniq = set(), []
        for n in it["needs"]:
            key = n["text"].strip()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(n)
        it["needs"] = uniq

    return {"items": items, "markers": sorted(used, key=lambda k: used[k]),
            "start": lo, "end": hi}


def paths_of(items: list[dict]) -> list[str]:
    """각 항목의 '상위 > 상위 > 자기' 경로. LLM 에게 맥락을 주는 데 쓴다."""
    out, stack = [], []
    for it in items:
        while stack and stack[-1][0] >= it["level"]:
            stack.pop()
        path = " > ".join([t for _, t in stack] + [it["title"]])
        out.append(path)
        stack.append((it["level"], it["title"]))
    return out


def score_note(hits: list[dict]) -> str:
    """짝지어진 심사배점을 집필카드에 실을 **한 문장**으로.

    왜 문장으로 박는가: 배점은 '무엇을 어느 무게로 써야 하는가'를 정하는 정보인데,
    지금까지는 분석 화면에서 보여만 주고 초고까지 가지 않았다. `purpose` 에 문장으로
    이어 붙이면 스키마를 바꾸지 않고 초고 프롬프트가 그대로 받는다.

    **짝짓기 확신이 낮으면 낮다고 적는다.** 유사도로 맞춘 것이라 틀릴 수 있고,
    틀린 배점을 확신에 차서 적어 두면 담당자가 엉뚱한 항목에 분량을 쏟는다.
    """
    if not hits:
        return ""
    parts, low = [], False
    for h in hits:
        pts = (h.get("points_text") or "").strip()
        if re.fullmatch(r"\d+(\.\d+)?", pts):      # 표에 숫자만 적힌 칸이 흔하다
            pts += "점"
        parts.append(f"‘{h.get('label') or h.get('score_item')}’" + (f" {pts}" if pts else ""))
        if (h.get("confidence") or 0) < 0.5:
            low = True
    out = "[심사배점] 이 항목은 " + ", ".join(parts) + "에 대응합니다."
    if low:
        out += " (짝짓기 확신이 낮으니 공고 원문에서 확인하세요.)"
    return out


_NOTE = re.compile(r"\[심사배점\]\s*이 항목은\s*(.+?)에 대응합니다\.")
_NOTE_PART = re.compile(r"‘([^’]+)’(?:\s*(\d+(?:\.\d+)?)\s*점)?")


def parse_score_note(purpose: str) -> list[dict]:
    """집필카드 purpose 에서 score_note() 가 박은 배점 문장을 되읽는다 → [{label, points(없으면 None), low}].

    왜 컬럼이 아니라 문장을 되읽는가: 배점은 지금 이 문장 하나로만 남아 있고, 사람이 카드에서 보고 고치는 것도
    이 문장이다. 따로 컬럼을 두면 화면의 문장과 집계가 어긋날 수 있다. 문장의 꼴을 정하는 score_note() 와
    되읽는 이 함수를 한 파일에 둔다 — 한쪽만 고치면 테스트가 깨진다."""
    out = []
    for m in _NOTE.finditer(purpose or ""):
        low = "확신이 낮" in (purpose[m.end():m.end() + 40])
        for p in _NOTE_PART.finditer(m.group(1)):
            out.append({"label": p.group(1).strip(), "points": float(p.group(2)) if p.group(2) else None, "low": low})
    return out


def to_tree(items: list[dict], refined: dict | None = None,
            scores: dict[int, list[dict]] | None = None) -> list[dict]:
    """평평한 항목 목록을 templates.py 와 **같은 모양**의 트리로 만든다.

    같은 모양으로 맞추는 이유: 목차를 심는 코드(프런트 buildFromTemplate,
    PUT /outline, replace-preview)를 그대로 재사용하기 위해서다.
    가이드라인은 새 문서 유형이 아니라 '그때그때 만들어지는 목차 틀'이다.

    scores: 항목 순번 → 짝지어진 배점 목록. 있으면 집필카드의 `purpose` 뒤에
            **이어 붙인다**(덮어쓰지 않는다 — 앞의 문장도 사람이 쓸 재료다).
    """
    root: list[dict] = []
    stack: list[tuple[int, dict]] = []          # (level, node)
    for idx, it in enumerate(items):
        r = (refined or {}).get(idx) or {}
        purpose = r.get("purpose", "")
        note = score_note((scores or {}).get(idx) or [])
        if note:
            purpose = f"{purpose}\n{note}" if purpose.strip() else note
        card = {
            "purpose": purpose,
            "question": r.get("question", ""),
            "message": "",
            "content": " ".join(it["instr"] + it["method"])[:800],
            "length": r.get("length", "") or "",
            "status": "작성 전",
        }
        node = {"title": it["title"], "children": [], "card": card,
                "_src": {"block": it["block"], "page": it["page"]}}
        while stack and stack[-1][0] >= it["level"]:
            stack.pop()
        (stack[-1][1]["children"] if stack else root).append(node)
        stack.append((it["level"], node))
    return root


# ────────────────────────── 배점표 ──────────────────────────
def parse_scoring(blocks: list[dict]) -> list[dict]:
    """배점표(표)에서 심사항목과 배점을 뽑는다.

    문단으로 읽으면 '배점 20'이 어느 지표 건지 사라진다. 그래서 표만 본다.
    doc_read 가 병합셀을 펼쳐 주므로 행 하나가 스스로 완결되어 있다.
    """
    out: list[dict] = []
    for b in blocks:
        if b["kind"] != "table" or len(b["rows"]) < 2:
            continue
        if table_lines(b["rows"]) is not None:      # 글상자는 배점표가 아니다
            continue
        head = [c.strip() for c in b["rows"][0]]
        joined = " ".join(head)
        if not (any(k in joined for k in SCORE_HEAD) and any(k in joined for k in SCORE_ITEM)):
            continue
        # 배점 칸과 항목 칸이 몇 번째인지 찾는다
        try:
            pcol = next(i for i, c in enumerate(head) if "배점" in c or "점수" in c)
        except StopIteration:
            continue
        icol = next((i for i, c in enumerate(head) if any(k in c for k in ("지표", "항목", "구분"))), 0)
        dcol = next((i for i, c in enumerate(head) if "세부" in c or "기준" in c), None)
        for row in b["rows"][1:]:
            if len(row) <= pcol:
                continue
            # 이름에는 세부기준 칸을 넣지 않는다(그것은 detail 로 따로 담는다).
            # '평가 항목 │ 세부 평가기준 │ 배점' 꼴에서 넣어 버리면 score_label() 이 마지막 마디인
            # 세부기준 문장을 이름으로 골라, 목차와 똑같은 항목명이 있어도 짝을 못 찾았다.
            names = [x for i, x in enumerate(row[:pcol]) if i != dcol and x.strip()]
            item = flat(" · ".join(dict.fromkeys(flat(x) for x in names)))[:120] or flat(row[icol])
            pts = row[pcol].strip()
            if not item.strip() or not pts:
                continue
            pts = flat(pts)
            m = re.search(r"(\d+(?:\.\d+)?)", pts)
            out.append({
                "item": item.strip(),
                "label": score_label(item),
                "points": float(m.group(1)) if m else None,
                "points_text": pts[:40],
                "detail": (flat(row[dcol])[:400] if dcol is not None and len(row) > dcol else ""),
                "block": b["i"],
            })
    # 병합셀을 펼친 탓에 같은 지표가 여러 행으로 나온다. 하나로 합치되
    # 세부 기준(산식 등)은 잃지 않고 이어 붙인다.
    merged: dict[tuple, dict] = {}
    for s in out:
        key = (s["item"], s["points_text"])
        if key in merged:
            prev = merged[key]["detail"]
            if s["detail"] and s["detail"] not in prev:
                merged[key]["detail"] = (prev + " / " + s["detail"]).strip(" /")[:600]
            continue
        merged[key] = s
    return list(merged.values())


# ────────────────────────── 사업 기본정보 후보 ──────────────────────────
BASIC_KEYS = {
    "접수마감": ("제출 기간", "접수 기간", "신청 기간", "접수기간", "제출기한", "신청서 접수"),
    "제출서류": ("제출 서류", "제출서류", "신청양식 구성", "제출 대상 서류"),
    "분량규정": ("이내로 작성", "page 이내", "쪽 이내", "포인트", "줄간격"),
    "신청자격": ("신청 자격", "공모 대상", "신청대상", "지원 대상", "수립대상", "추진 방향"),
    "지원규모": ("지원 규모", "사업비", "예산 범위", "국비", "총사업비"),
}


def parse_basic(blocks: list[dict]) -> dict:
    """기본정보 '후보'를 모은다. 확정하지 않는다 — 사람이 고른다."""
    found: dict[str, list[dict]] = {k: [] for k in BASIC_KEYS}
    for b in blocks:
        t = b["text"]
        if not (10 <= len(t) <= 400):
            continue
        for key, words in BASIC_KEYS.items():
            if any(w in t for w in words):
                found[key].append({"text": t[:300], "block": b["i"], "page": b["page"]})
                break
    out = {}
    for key, hits in found.items():
        if not hits:
            continue
        out[key] = hits[:4]
    # 마감일 후보(업무의 due_date 로 쓸 것). 접수 기간은 '시작 ~ 마감'이므로
    # 가장 늦은 날짜가 마감이다. 고르는 것은 사람이 한다.
    dates = []
    for h in found.get("접수마감", []):
        dates += dates_in(h["text"])
    out["마감일후보"] = sorted(set(dates))
    return out


def analyze_rules(blocks: list[dict], start: int | None = None, end: int | None = None) -> dict:
    """규칙 단계 전부. LLM 없이 여기까지 나온다."""
    parsed = parse_outline(blocks, start, end)
    scoring = parse_scoring(blocks)
    return {
        "outline": parsed,
        "tree": to_tree(parsed["items"]),
        "scoring": scoring,
        "scoring_match": match_scoring(parsed["items"], scoring),
        "basic": parse_basic(blocks),
    }


# ────────────────────────── 배점 ↔ 목차 짝짓기 ──────────────────────────
def match_scoring(items: list[dict], scoring: list[dict], threshold: float = 0.34) -> dict:
    """심사항목과 목차 항목을 짝짓는다. 짝이 **안 맞는 쪽이 더 중요하다.**

    · 배점에 걸리지 않는 목차 → 분량을 줄여도 되는 항목
    · 대응 목차가 없는 배점  → **빠뜨린 항목**. 공모에서 감점·반려의 실제 원인이다.

    hwpx_form.propose() 와 같은 방식으로 확신도(score)와 이유(why)를 함께 낸다.
    심사항목 다섯에 목차 열둘인 것이 보통이므로 1:1 이 아니다 — 목차 여럿이
    같은 심사항목에 걸릴 수 있게 둔다(반대로 한 목차는 한 심사항목에만 건다).
    """
    from .hwpx_form import similarity

    pairs, unmatched_scores = [], []
    hit_nodes: set[int] = set()
    for s in scoring:
        # 짝지을 말 후보: 구체 마디 + 세부기준의 첫 구절
        keys = [s.get("label") or s["item"]]
        head = re.split(r"[/,·]|\s및\s", (s.get("detail") or "").lstrip("▪■◦○ ").strip())
        if head and len(head[0].strip()) >= 4:
            keys.append(head[0].strip()[:40])
        best, bscore = None, 0.0
        for idx, it in enumerate(items):
            sc = max(similarity(k, it["title"]) for k in keys)
            if sc > bscore:
                best, bscore = idx, sc
        if best is not None and bscore >= threshold:
            hit_nodes.add(best)
            pairs.append({"score_item": s["item"], "label": s.get("label") or s["item"],
                          "points": s["points"],
                          "points_text": s["points_text"], "detail": s["detail"],
                          "node_index": best, "node_title": items[best]["title"],
                          "confidence": round(bscore, 2),
                          "why": f"‘{s.get('label') or s['item']}’ ↔ 목차 ‘{items[best]['title']}’ (유사도 {bscore:.2f})"})
        else:
            unmatched_scores.append({"score_item": s["item"], "label": s.get("label") or s["item"],
                                     "points": s["points"],
                                     "points_text": s["points_text"], "detail": s["detail"]})
    unmatched_nodes = [{"node_index": i, "node_title": it["title"]}
                       for i, it in enumerate(items) if i not in hit_nodes]
    return {"pairs": pairs,
            "missing_in_outline": unmatched_scores,
            "unscored_nodes": unmatched_nodes}
