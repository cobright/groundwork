# -*- coding: utf-8 -*-
"""주민 설문 — 규칙으로 하는 일 한 곳(점검 · 목표 응답 수 · 폼으로 옮기기 표).

설계: docs/design/survey.md. 여기 있는 것은 전부 **규칙**이다(AI 를 부르지 않는다).
문서 8장의 순서대로 'AI 없이도 끝까지 도는 뼈대'를 먼저 세운다 — AI 제안(문항 제안·점검)은
그 위에 얹는다. 폴백이 있어야 '빠른 길'이 막히지 않는다(담당자 진술·가이드라인과 같은 이유).

점검은 검토자와 같다: **의견만** 낸다. 문항을 고치지 않는다(원칙 1).
"""
from __future__ import annotations

import json
import math
import re

QTYPES = ["단일", "복수", "척도", "순위", "숫자", "주관식"]
CHOICE = {"단일", "복수", "척도", "순위"}          # 보기가 있어야 하는 유형
BASES = ["미정", "설문", "통계", "진술"]
METHODS = ["온라인 폼", "현장 대리 입력", "온라인 폼 + 현장 대리 입력", "종이 설문"]

# 어림 응답 시간(초). 정밀한 값이 아니다 — 화면에도 '어림'이라고 적는다.
_SECONDS = {"단일": 10, "척도": 10, "숫자": 12, "복수": 18, "순위": 30, "주관식": 45}

_PERSONAL = re.compile(r"성명|이름|연락처|전화|휴대폰|핸드폰|주소|이메일|e-?mail", re.I)
_LEADING = re.compile(r"지\s*않습니까|않으십니까|않겠습니까|당연히|꼭\s*필요한")
_DOUBLE = re.compile(r"\S\s*(및|그리고)\s*\S")
_ELDERLY = re.compile(r"어르신|노인|고령|경로당|70\s*대|80\s*대|65\s*세")


def loads(s, default):
    try:
        v = json.loads(s or "")
        return v if isinstance(v, type(default)) else default
    except (ValueError, TypeError):
        return default


def target_n(population: int, margin: float, z: float = 1.96) -> int:
    """대상 인구와 오차범위(±%p)로 필요한 응답 수. 95% 신뢰수준, 가장 보수적인 p=0.5.

    유한 모집단 보정을 한다 — 군 단위 대상은 수천 명이라 보정 여부로 결과가 꽤 달라진다
    (예: 6,100명 · ±5%p → 보정 없이 385명, 보정하면 362명).
    """
    if not margin or margin <= 0:
        return 0
    e = margin / 100.0
    n0 = z * z * 0.25 / (e * e)
    if population and population > 0:
        n0 = n0 / (1 + (n0 - 1) / population)
    return int(math.ceil(n0))


def margin_of(n: int, population: int = 0, z: float = 1.96) -> float:
    """응답 n 개의 오차범위(±%p). 수집 중·결과 인용에 쓴다(5장 '숫자의 조건')."""
    if n <= 0:
        return 0.0
    e = z * math.sqrt(0.25 / n)
    if population and population > n:
        e *= math.sqrt((population - n) / (population - 1))
    return round(e * 100, 1)


# ────────────── ③ 점검 ──────────────
def _op(level, kind, text, qid=None, cid=None):
    return {"level": level, "kind": kind, "text": text, "question_id": qid, "claim_id": cid}


def check(survey: dict, claims: list[dict], questions: list[dict]) -> list[dict]:
    """문항 품질 · 구조 · 분량 · 대상에 대한 의견. level: 중요/일반/참고.

    '받치는 주장이 없는 문항'과 '문항이 없는 주장'을 짚는 것이 핵심이다 —
    설계한 설문지가 곧 분석 틀이 되려면 그 둘이 맞물려 있어야 한다(설계 문서 2장).
    """
    out: list[dict] = []
    qids = {q["id"] for q in questions}
    order = {q["id"]: i for i, q in enumerate(questions)}
    num = {q["id"]: i + 1 for i, q in enumerate(questions)}

    for q in questions:
        qid, n = q["id"], num[q["id"]]
        text = (q.get("text") or "").strip()
        opts = [o.strip() for o in q.get("options") or []]
        tag = f"{n}번"
        if not text:
            out.append(_op("중요", "문항", f"{tag} 문항의 글이 비어 있습니다.", qid))
            continue
        if q["qtype"] in CHOICE:
            filled = [o for o in opts if o]
            if len(filled) < 2:
                out.append(_op("중요", "문항", f"{tag} '{q['qtype']}' 문항인데 보기가 {len(filled)}개입니다.", qid))
            dup = sorted({o for o in filled if filled.count(o) > 1})
            if dup:
                out.append(_op("중요", "문항", f"{tag} 보기가 겹칩니다: {', '.join(dup)}", qid))
            if len(filled) != len(opts):
                out.append(_op("일반", "문항", f"{tag} 빈 보기가 있습니다.", qid))
        # 예/아니오처럼 보기가 둘뿐인 문항에는 '기타'가 들어갈 자리가 없다(짚으면 소음이다).
        if q["qtype"] in ("단일", "복수") and not q.get("other_allowed") and len(opts) >= 3 \
                and not any(o.startswith("기타") for o in opts) and not q.get("profile"):
            out.append(_op("참고", "문항", f"{tag} '기타'가 없습니다 — 보기 밖의 답을 가진 사람이 아무 보기나 고르게 됩니다.", qid))
        if q["qtype"] == "척도":
            k = len([o for o in opts if o])
            if k and not 3 <= k <= 7:
                out.append(_op("일반", "문항", f"{tag} 척도가 {k}단계입니다. 보통 5단계(또는 4·7단계)를 씁니다.", qid))
        if q["qtype"] == "순위" and opts and q.get("rank_k", 3) > len(opts):
            out.append(_op("일반", "문항", f"{tag} 보기({len(opts)}개)보다 많은 순위({q['rank_k']}순위)를 받습니다.", qid))
        if _DOUBLE.search(text):
            out.append(_op("참고", "문항", f"{tag} '및·그리고'가 있습니다 — 두 가지를 한꺼번에 묻고 있지 않은지 보세요"
                                          f"(한쪽만 만족하는 사람은 답할 수 없습니다).", qid))
        if _LEADING.search(text):
            out.append(_op("일반", "문항", f"{tag} 답을 이끄는 말투로 보입니다 — 결과가 '그렇게 물었으니 그렇게 나왔다'로 읽힙니다.", qid))
        if _PERSONAL.search(text):
            out.append(_op("중요", "개인정보", f"{tag} 개인정보를 묻는 것으로 보입니다. 꼭 필요하면 수집·이용 동의 문항을 앞에 두고, "
                                            f"분석 파일과 따로 관리하세요(기본은 묻지 않는 것).", qid))

        # 구조: 받치는 주장
        if not q.get("claim_id") and not q.get("profile"):
            out.append(_op("일반", "구조", f"{tag} 받치는 주장이 없습니다 — 계획서 어디에도 쓰지 않을 문항이면 빼는 편이 응답률에 낫습니다.", qid))

        # 분석 계획: 가리키는 문항이 살아 있는가
        for x in q.get("cross_with") or []:
            if x not in qids:
                out.append(_op("중요", "분석", f"{tag} 분석 계획이 지워진 문항을 가리킵니다 — 다시 고르세요.", qid))
            elif x == qid:
                out.append(_op("일반", "분석", f"{tag} 분석 계획이 자기 자신을 가리킵니다.", qid))

        # 분기: 폼의 '답변을 기준으로 섹션 이동'은 객관식(단일)에만 있다
        br = q.get("branch") or {}
        if br and q["qtype"] != "단일":
            out.append(_op("중요", "분기", f"{tag} 분기는 단일 선택 문항에서만 폼으로 옮길 수 있습니다.", qid))
        for opt, to in br.items():
            if opt not in opts:
                out.append(_op("중요", "분기", f"{tag} 분기 조건의 보기 '{opt}'가 보기 목록에 없습니다(보기 글을 고쳤을 수 있습니다).", qid))
            if to == "end":
                continue
            if to not in qids:
                out.append(_op("중요", "분기", f"{tag} '{opt}' 응답의 이동 대상 문항이 지워졌습니다.", qid))
            elif order[to] <= order[qid]:
                out.append(_op("중요", "분기", f"{tag} '{opt}' 응답이 앞 문항({num[to]}번)으로 돌아갑니다 — 응답자가 같은 자리를 맴돕니다.", qid))

    # 구조: 문항이 없는 주장 · 정하지 않은 주장
    used = {q.get("claim_id") for q in questions}
    for c in claims:
        label = f"주장 ‘{(c.get('claim') or '').strip()[:30] or '(빈 주장)'}’"
        if c["basis"] == "설문" and c["id"] not in used:
            out.append(_op("중요", "구조", f"{label}은 설문으로 받치기로 했는데 문항이 없습니다.", cid=c["id"]))
        elif c["basis"] == "미정":
            out.append(_op("참고", "구조", f"{label}을 무엇으로 받칠지 아직 정하지 않았습니다.", cid=c["id"]))
        if c["basis"] == "통계" and c["id"] in used:
            out.append(_op("일반", "구조", f"{label}은 통계로 받치기로 했는데 문항이 붙어 있습니다 — "
                                          f"통계로 증명할 수 있는 것을 설문으로 재면 틀리고 문항만 길어집니다.", cid=c["id"]))

    # 응답자 특성: 분석 계획이 '× 연령대·× 읍면' 을 쓰려면 있어야 하고, 보기는 통계 구분과 같아야 한다
    profiles = [q for q in questions if q.get("profile")]
    if questions and not profiles:
        out.append(_op("일반", "구조", "응답자 특성 문항(연령대·지역 등)이 없습니다 — 결과를 실제 인구와 견줄 수 없어 "
                                     "설득력이 약해집니다. 수집이 끝난 뒤에는 되살릴 수 없습니다."))
    elif profiles:
        names = ", ".join(f"{num[q['id']]}번" for q in profiles)
        out.append(_op("참고", "구조", f"응답자 특성 문항({names})의 보기는 주민등록 통계의 구분과 **똑같이** 만드세요 "
                                     f"(예: 연령 10세 구간, 지역(읍·면 등) 이름 그대로). 그래야 응답자 구성과 실제 인구를 나란히 놓을 수 있습니다."))

    # 분량
    if questions:
        sec = sum(_SECONDS.get(q["qtype"], 15) for q in questions)
        mins = max(1, round(sec / 60))
        if mins > 10 or len(questions) > 30:
            out.append(_op("일반", "분량", f"문항 {len(questions)}개, 어림 응답 시간 약 {mins}분 — 길면 끝까지 답하지 않는 사람이 늘어납니다."))

    # 대상과 방식
    tgt = (survey.get("target") or "") + " " + (survey.get("title") or "")
    if _ELDERLY.search(tgt) and survey.get("method") == "온라인 폼":
        out.append(_op("일반", "대상", "대상이 고령층으로 보이는데 방식이 온라인 폼뿐입니다. 담당자·도우미가 현장에서 태블릿으로 "
                                     "**같은 폼에** 대신 입력하는 방식을 더하면 응답이 한곳에 모입니다."))
    if not survey.get("population"):
        out.append(_op("참고", "대상", "대상 인구를 적으면 목표 응답 수를 계산해 드립니다."))

    rank = {"중요": 0, "일반": 1, "참고": 2}
    out.sort(key=lambda o: rank.get(o["level"], 9))
    return out


# ────────────── ④ 폼으로 옮기기 ──────────────
def _form_type(q: dict) -> str:
    """구글폼의 유형 이름으로. 네이버폼 이름은 실물을 보고 붙인다(짐작한 이름을 적지 않는다)."""
    t = q["qtype"]
    opts = [o for o in q.get("options") or [] if o.strip()]
    if t == "단일":
        return "객관식 질문"
    if t == "복수":
        return "체크박스"
    if t == "척도":
        if 2 <= len(opts) <= 10:
            return f"선형 배율 (1~{len(opts)}, 왼쪽 ‘{opts[0]}’ · 오른쪽 ‘{opts[-1]}’)"
        return "객관식 질문"
    if t == "순위":
        k = min(q.get("rank_k") or 3, len(opts) or 1)
        return f"객관식 그리드 (행=보기, 열=1순위~{k}순위, ‘열당 응답 1개로 제한’ 켜기)"
    if t == "숫자":
        return "단답형 (응답 확인 → 숫자)"
    return "장문형"


def form_rows(questions: list[dict]) -> list[dict]:
    """문항을 폼 섹션으로 나누고, 옮겨 적을 칸을 채운다.

    구글폼의 분기는 '문항'이 아니라 '섹션'으로 이동한다. 그래서
      · 분기 문항은 그 섹션의 마지막에 와야 하고(뒤에 문항이 있으면 이동 전에 그것까지 보인다),
      · 분기로 가는 대상 문항은 섹션의 첫 문항이어야 한다.
    이 두 곳에서 섹션을 끊는다.
    """
    targets = set()
    for q in questions:
        for to in (q.get("branch") or {}).values():
            if to != "end":
                targets.add(to)
    sec = 0
    sec_of: dict[int, int] = {}
    prev_branch = True                       # 첫 문항은 1 섹션의 시작
    for q in questions:
        if prev_branch or q["id"] in targets:
            sec += 1
        sec_of[q["id"]] = sec
        prev_branch = bool(q.get("branch"))
    num = {q["id"]: i + 1 for i, q in enumerate(questions)}

    rows = []
    for q in questions:
        opts = [o for o in q.get("options") or [] if o.strip()]
        br = q.get("branch") or {}
        moves = []
        if br:
            for o in opts:
                to = br.get(o)
                if to == "end":
                    moves.append(f"{o} → 양식 제출")
                elif to in sec_of:
                    moves.append(f"{o} → 섹션 {sec_of[to]}({num[to]}번)")
                else:
                    moves.append(f"{o} → 다음 섹션")
        rows.append({
            "no": num[q["id"]], "id": q["id"], "section": sec_of[q["id"]],
            "text": q.get("text") or "", "qtype": q["qtype"], "form_type": _form_type(q),
            "options": opts if q["qtype"] not in ("숫자", "주관식") else [],
            "required": bool(q.get("required")),
            "other": bool(q.get("other_allowed")) and q["qtype"] in ("단일", "복수"),
            "moves": moves,
        })
    return rows


def checklist(survey: dict, questions: list[dict], rows: list[dict]) -> list[dict]:
    """폼을 만든 뒤 설정에서 확인할 것. 정답이 정해진 것이 아니라 **정해야 할 것**의 목록이다."""
    personal = any(_PERSONAL.search(q.get("text") or "") for q in questions)
    branched = any(q.get("branch") for q in questions)
    proxy = "대리" in (survey.get("method") or "")
    req = sum(1 for q in questions if q.get("required"))
    items = [
        ("응답 횟수 1회로 제한", "켜면 응답자가 구글 계정으로 로그인해야 합니다. 어르신 응답·현장 대리 입력이 있으면 "
                           "끄고, 중복 응답은 정리 단계에서 후보로 표시합니다." if proxy else
                           "켜면 응답자가 구글 계정으로 로그인해야 합니다 — 대상이 로그인에 익숙한지 보고 정하세요."),
        ("이메일 주소 수집", "끄는 것이 기본입니다(개인정보). 경품 등으로 꼭 받아야 하면 동의 문항과 함께."),
        ("필수 응답", f"필수 문항 {req}개 / 전체 {len(questions)}개 — 폼에서 같은 문항에 '필수'가 켜졌는지 확인하세요."),
        ("응답 마감", f"{survey.get('period_to')} 에 '응답 받기'를 끕니다." if survey.get("period_to")
                    else "조사 기간 끝 날을 정해 두세요(마감 뒤 응답이 섞이면 조사 개요가 거짓이 됩니다)."),
        ("응답 시트 연결", "응답을 스프레드시트로 받게 해 두세요. 나중에 그 파일을 워크벤치에 올려 정리·집계합니다."),
    ]
    if personal:
        items.insert(2, ("개인정보 수집·이용 동의", "개인정보를 묻는 문항이 있습니다. 첫 섹션에 동의 문항(동의하지 않으면 양식 제출)을 두세요."))
    if branched:
        n_sec = max((r["section"] for r in rows), default=1)
        items.append(("섹션 끝의 이동", f"섹션이 {n_sec}개입니다. 분기로 갈라진 뒤 다시 합쳐질 자리는 각 섹션 아래의 "
                                     f"'섹션 ○ 이후' 설정으로 정합니다 — 폼의 '미리보기'로 갈래마다 끝까지 눌러 보세요."))
    if proxy:
        items.append(("현장 대리 입력 구분", "대리 입력인지 알 수 있게 마지막에 '응답 방식(본인/대리 입력)' 문항을 두면, "
                                        "결과에 방식별 비율을 적을 수 있습니다(설득력 장치)."))
    items.append(("네이버폼으로 만들 때", "유형 이름이 구글폼과 다를 수 있습니다. 문항·보기·분기는 이 표 그대로 옮기면 됩니다."))
    return [{"item": a, "note": b} for a, b in items]
