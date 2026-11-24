# -*- coding: utf-8 -*-
"""시험용 **가상 보고서 양식(.hwpx)** 을 만든다.

실제 기관 양식은 공개 저장소에 넣을 수 없으므로, 양식 채우기(services/hwpx_fill.py)가 읽는 구조만
갖춘 가상 양식을 그때그때 만든다. 뼈대(글꼴·구역 설정)는 모의데이터 01 공고 hwpx 의 것을 빌린다.

넣어 둔 구조:  제목 상자(두 줄) · 날짜 자리표시 · '기관명' · 목차 표(옛 장 2개 + 옛 하위 항목 + [붙 임] 꼬리)
             · '제 목' 표 · 장 제목 표 2개(1행 3칸, 첫 장에 쪽번호 재시작) · 개조식 □ ○ ― ※ (앞공백 0·2·3·5)
함정:       모든 문단에 줄바꿈 캐시(linesegarray)를 넣어 둔다 — 손댄 문단에 남으면 한글에서 깨진다.
"""
import io
import re
import zipfile

from conftest import MOCK

LINESEG = ('<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
           'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray>')


def _p(*runs: str, extra: str = "") -> str:
    body = "".join(f'<hp:run charPrIDRef="94">{r}</hp:run>' for r in runs)
    return (f'<hp:p id="0" paraPrIDRef="84" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'{body}{extra}{LINESEG}</hp:p>')


def _t(text: str) -> str:
    return f"<hp:t>{text}</hp:t>"


def _table(cells: list[list[str]], ctrl: str = "") -> str:
    """1행 N칸 표를 담은 문단. cells: 칸마다 문단 XML 목록."""
    tcs = "".join(f'<hp:tc><hp:subList>{"".join(ps)}</hp:subList></hp:tc>' for ps in cells)
    tbl = f'<hp:tbl rowCnt="1" colCnt="{len(cells)}"><hp:tr>{tcs}</hp:tr></hp:tbl>'
    return (f'<hp:p id="0" paraPrIDRef="84" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="94">{ctrl}{tbl}</hp:run></hp:p>')


def _toc_item(roman: str, title: str, page: str) -> str:
    return _p(_t(roman), f'<hp:t>{title}<hp:tab width="4000" leader="3" type="2"/>{page}</hp:t>')


def make_form() -> bytes:
    base = next(MOCK.glob("01_*.hwpx"))
    zin = zipfile.ZipFile(base)
    sec = zin.read("Contents/section0.xml").decode("utf-8")
    head = sec[: sec.index("</hp:p>") + len("</hp:p>")]          # 루트 여는 태그 + 구역 설정 문단
    paras = [
        _table([[_p(_t("보고서 양식(제목)")), _p(_t("부제 둘째 줄"))]]),
        _p(_t("2026. 1. 1.")),
        _p(_t("기관명")),
        _table([[_p(_t("목 차")),
                 _toc_item("Ⅰ", ". 옛 첫 장", "3"),
                 _p(f'<hp:t>1. 옛 하위 항목<hp:tab width="4000" leader="3" type="2"/>4</hp:t>'),
                 _toc_item("Ⅱ", ". 옛 둘째 장", "7"),
                 _p('<hp:t>[붙 임] 별지 서식 안내<hp:tab width="4000" leader="3" type="2"/>9</hp:t>')]]),
        _table([[_p(_t("제 목"))]]),
        _table([[_p(_t("Ⅰ"))], [_p(_t(""))], [_p(_t(" 옛 첫 장 제목"))]],
               ctrl='<hp:ctrl><hp:newNum num="1" numType="PAGE"/></hp:ctrl>'),
        _p(_t("□ "), _t("옛 항목")),                               # □ 는 기호·본문 run 이 나뉜 양식이 많다
        _p(_t("  ○ 옛 내용")),
        _p(_t("   ― 옛 세부")),
        _p(_t("     ※ 옛 주석")),
        _table([[_p(_t("Ⅱ"))], [_p(_t(""))], [_p(_t(" 옛 둘째 장 제목"))]]),
        _p(_t("□ "), _t("옛 둘째 내용")),
    ]
    new_sec = head + "".join(paras) + "</hs:sec>"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for info in zin.infolist():                                 # 원본 순서·압축 방식 그대로
            data = new_sec.encode("utf-8") if info.filename == "Contents/section0.xml" else zin.read(info)
            z.writestr(info, data)
    return buf.getvalue()


def strip_ns(xml: str) -> str:
    return re.sub(r"\s+xmlns:\w+=\"[^\"]+\"", "", xml)
