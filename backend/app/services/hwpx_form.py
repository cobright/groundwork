# -*- coding: utf-8 -*-
"""서식형 HWPX 양식(신청서·사업계획서 서식) 분석과 자동 배정.

왜 별도인가:
  보고서 양식(hwpx_fill.py)은 '장 + 개조식'이라는 뼈대가 있어 구조를 복제하면 된다.
  반면 공공기관 서식은 **사업마다 기관마다 다르다**. 표준이 없다. 그러므로
  "이런 모양일 것"이라 가정하지 않고, 주어진 양식을 그때그때 읽어 자리를 찾는다.

원칙:
  · 사람의 수작업을 최대한 덜어준다 → 자동으로 끝까지 배정해 '제안'을 만든다.
  · 그러나 확정은 사람이 한다 → 제안에는 근거(왜 이렇게 짝지었는지)와 확신도를 함께 낸다.
  · 모르는 것은 지어내지 않는다 → 확신이 낮으면 비워 두고 그 사실을 드러낸다.

읽어내는 것:
  구획(zone)  — 배너(제목 표)로 나뉜 문서의 덩어리. 안내문인지 채우는 곳인지 판정한다.
  자리(slot)  — 채우는 구획 안의 두 종류
                field   : 표에서 '라벨 옆 빈칸'  (기관명 → □)
                section : 번호 매긴 문단 아래     (2. 사업의 필요성 → 그 아래 본문)
"""
from __future__ import annotations

import io
import re
import zipfile
import defusedxml.ElementTree as ET   # 파싱은 안전한 쪽으로(XXE·XML 폭탄)

P = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

SECTION_RE = re.compile(r"^\s*(\d+)\s*[.)]\s*(.+)")
GUIDE_RE = re.compile(r"작성|서술|기재|명시|표현|포함할 것|적을 것|입력|서식|참조")
HANGUL_RE = re.compile(r"[가-힣]")
NOISE_HEAD = "※󰠂◦·­■□▶●○-–—"

# 라벨 → 우리가 아는 값. 서식마다 말이 조금씩 달라 여러 표기를 함께 둔다.
FIELD_DICT = {
    "project_name": ("사업명", "사 업 명", "과제명", "사업 명", "프로그램명", "사업제목"),
    "org_name": ("기관명", "기 관 명", "신청기관", "신청기관명", "단체명", "소속기관", "기관"),
    "author_name": ("담당자", "담당자명", "작성자", "성명", "성  명", "담당"),
    "due_date": ("사업기간", "기간", "사업 기간", "추진기간"),
    "today": ("작성일", "신청일", "작성일자", "제출일"),
}
# 우리가 알 수 없는 것들(연락처·계좌 등)은 아예 후보로 두지 않는다.
UNKNOWN_LABELS = ("연락처", "전화", "휴대폰", "fax", "팩스", "e-mail", "이메일",
                  "주소", "번호", "계좌", "생년월일", "성별")


# ────────────── 문자열 도우미 ──────────────
def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(P + "t"))


def _cell_text(tc) -> str:
    sub = tc.find(P + "subList")
    return "" if sub is None else "\n".join(_text(q) for q in sub.findall(P + "p")).strip()


def _norm(s: str) -> str:
    """비교용 정규화: 번호·괄호·공백·기호를 걷어낸다."""
    s = SECTION_RE.sub(r"\2", s or "")
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", s)
    return s


# 글자가 달라도 같은 것을 가리키는 행정 용어들
SYNONYMS = [
    ("예산", "사업비", "소요예산", "신청금액", "총사업비", "재원"),
    ("일정", "기간", "추진일정", "사업기간", "실행일정"),
    ("기대효과", "성과", "효과"),
    ("추진배경", "배경", "필요성", "추진 배경"),
    ("추진계획", "사업내용", "세부사업내용", "주요사업내용", "세부 추진계획"),
    ("평가", "평가방법", "성과관리"),
    ("대상", "사업대상", "주요대상", "사업 대상과 범위"),
]


def _syn_boost(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    for group in SYNONYMS:
        ga = any(_norm(w) and _norm(w) in na for w in group)
        gb = any(_norm(w) and _norm(w) in nb for w in group)
        if ga and gb:
            return 0.45
    return 0.0


def similarity(a: str, b: str) -> float:
    """두 글자씩 겹치는 비율(Dice). 한국어 제목 비교에 무난하다."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    ga = {a[i:i + 2] for i in range(len(a) - 1)} or {a}
    gb = {b[i:i + 2] for i in range(len(b) - 1)} or {b}
    dice = 2 * len(ga & gb) / (len(ga) + len(gb))
    return min(1.0, dice + _syn_boost(a, b))


# ────────────── 구획 나누기 ──────────────
def _banner_of(top) -> str | None:
    """이 문단의 표가 '구획 제목'인가. 칸이 적고 짧은 한글 제목이면 그렇다."""
    for tbl in top.findall(f".//{P}tbl"):
        cells = tbl.findall(f".//{P}tc")
        if len(cells) > 3:
            continue
        texts = [_cell_text(tc) for tc in cells]
        head = max(texts, key=len) if texts else ""
        if (2 <= len(head) <= 40 and head.count("\n") <= 1
                and HANGUL_RE.search(head) and not SECTION_RE.match(head)):
            return head.replace("\n", " ").strip()
    return None


def _zone_stats(items):
    """칸/빈칸 수와, 섹션 헤더 아래가 '이미 채워져 있는지'를 센다.

    안내문과 채우는 곳을 가르는 가장 확실한 신호는 이것이다:
    안내문은 각 항목 아래에 설명이 꽉 차 있고, 채우는 곳은 항목 아래가 비어 있다.
    """
    cells = blanks = guides = 0
    filled_after = empty_after = 0
    plain = [(i, t) for i, t in items if t.find(f".//{P}tbl") is None]
    for _, top in items:
        for tc in top.findall(f".//{P}tc"):
            cells += 1
            if not _cell_text(tc):
                blanks += 1
        if top.find(f".//{P}tbl") is None:
            t = _text(top).strip()
            if t and GUIDE_RE.search(t):
                guides += 1
    for k, (_, top) in enumerate(plain):
        t = _text(top).strip()
        if not t or not SECTION_RE.match(t) or t[0] in NOISE_HEAD:
            continue
        nxt = _text(plain[k + 1][1]).strip() if k + 1 < len(plain) else ""
        # 다음 줄이 설명(◦ 등)으로 이미 채워져 있으면 '안내', 비었거나 또 다른 항목이면 '채움'
        if nxt and not SECTION_RE.match(nxt) and nxt[0] in NOISE_HEAD:
            filled_after += 1
        else:
            empty_after += 1
    return cells, blanks, guides, filled_after, empty_after


def split_zones(root) -> list[dict]:
    """배너를 경계로 문서를 구획으로 나누고, 각 구획이 채우는 곳인지 판정한다."""
    tops = root.findall(f"./{P}p")
    zones, cur = [], {"title": "(머리말)", "start": 0, "items": []}
    for i, top in enumerate(tops):
        banner = _banner_of(top) if top.find(f".//{P}tbl") is not None else None
        if banner:
            zones.append(cur)
            cur = {"title": banner, "start": i, "items": []}
            continue
        cur["items"].append((i, top))
    zones.append(cur)

    out = []
    for z in zones:
        cells, blanks, guides, filled, empty = _zone_stats(z["items"])
        # 채우는 곳: 표에 빈칸이 있거나, 항목 아래가 비어 사람이 쓸 자리가 있는 곳.
        # 항목마다 설명이 이미 달린 구획은 안내문이므로 건드리지 않는다.
        z["fillable"] = blanks > 0 or empty > filled
        z["cells"], z["blanks"], z["guides"] = cells, blanks, guides
        z["filled_after"], z["empty_after"] = filled, empty
        out.append(z)
    return out


# ────────────── 자리 찾기 ──────────────
def _is_unknown_label(label: str) -> bool:
    low = label.replace(" ", "").lower()
    return any(k in low for k in UNKNOWN_LABELS)


def find_slots(root) -> tuple[list[dict], list[dict]]:
    """(구획 목록, 자리 목록). 자리는 채우는 구획 안에서만 찾는다."""
    zones = split_zones(root)
    slots = []
    for zi, z in enumerate(zones):
        if not z["fillable"]:
            continue
        for pi, top in z["items"]:
            if top.find(f".//{P}tbl") is not None:
                for ti, tbl in enumerate(top.findall(f".//{P}tbl")):
                    for ri, tr in enumerate(tbl.findall(P + "tr")):
                        cells = tr.findall(P + "tc")
                        texts = [_cell_text(tc) for tc in cells]
                        for ci in range(len(cells) - 1):
                            label, value = texts[ci], texts[ci + 1]
                            if not label or value:
                                continue
                            if len(label) > 16 or label[0] in NOISE_HEAD:
                                continue
                            if not HANGUL_RE.search(label):
                                continue
                            slots.append({
                                "id": f"f{pi}-{ti}-{ri}-{ci + 1}",
                                "kind": "field", "zone": zi, "zone_title": z["title"],
                                "label": label.replace("\n", " "),
                                "addr": [pi, ti, ri, ci + 1],
                                "unknown": _is_unknown_label(label),
                            })
            else:
                t = _text(top).strip()
                if not t or t[0] in NOISE_HEAD:
                    continue
                m = SECTION_RE.match(t)
                if m:
                    body = m.group(2).strip()
                    # '1. 사업명' 처럼 한 줄 값이 들어가는 항목은 섹션이 아니라 값 자리다.
                    as_field = any(similarity(body, n) >= 0.85
                                   for names in FIELD_DICT.values() for n in names)
                    slots.append({
                        "id": f"s{pi}", "kind": "field" if as_field else "section",
                        "zone": zi, "zone_title": z["title"], "label": body if as_field else t.strip(),
                        "addr": [pi], "unknown": False,
                        "after_para": as_field,      # 문단 '아래'에 값을 넣는 자리
                    })
    return zones, slots


# ────────────── 자동 배정(제안) ──────────────
def propose(slots: list[dict], outline: list[dict], values: dict,
            threshold: float = 0.34) -> list[dict]:
    """각 자리에 무엇을 넣을지 자동으로 제안한다.

    outline : [{uid, title, number, has_body}] — 우리 목차
    values  : {"project_name": …, "org_name": …, "author_name": …, "due_date": …, "today": …}
    제안에는 왜 그렇게 짝지었는지(why)와 확신도(score)를 함께 담아 사람이 판단할 수 있게 한다.
    """
    used = set()
    out = []
    for s in slots:
        pick = {"slot": s["id"], "source": "", "value": "", "uid": "", "score": 0.0, "why": ""}
        if s["kind"] == "field":
            if s["unknown"]:
                pick["why"] = "우리가 알 수 없는 값(연락처 등) — 비움"
            else:
                best, bkey, bscore = "", "", 0.0
                for key, names in FIELD_DICT.items():
                    sc = max(similarity(s["label"], n) for n in names)
                    if sc > bscore:
                        best, bkey, bscore = values.get(key, ""), key, sc
                if bscore >= 0.6 and best:
                    pick.update(source=bkey, value=best, score=round(bscore, 2),
                                why=f"‘{s['label']}’ 을(를) {bkey} 로 봄")
                elif bscore >= 0.6:
                    pick["why"] = f"‘{s['label']}’ 에 해당하는 값이 아직 비어 있음"
                else:
                    pick["why"] = "짝지을 값을 찾지 못함"
        else:
            best, bscore = None, 0.0
            for node in outline:
                sc = similarity(s["label"], node["title"])
                if sc > bscore:
                    best, bscore = node, sc
            if best and bscore >= threshold and best["uid"] not in used:
                used.add(best["uid"])
                pick.update(source="outline", uid=best["uid"], value=best["title"],
                            score=round(bscore, 2),
                            why=f"‘{s['label']}’ ↔ 목차 ‘{best['title']}’ (유사도 {bscore:.2f})")
            elif best and bscore >= threshold:
                pick.update(score=round(bscore, 2),
                            why=f"목차 ‘{best['title']}’ 은 이미 다른 자리에 배정됨")
            else:
                pick["why"] = "맞는 목차를 찾지 못함 — 비움"
        out.append(pick)
    return out


def load_root(form_bytes: bytes):
    with zipfile.ZipFile(io.BytesIO(form_bytes)) as z:
        return ET.fromstring(z.read("Contents/section0.xml"))
