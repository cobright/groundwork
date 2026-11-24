# -*- coding: utf-8 -*-
"""문서 읽기(services/doc_read.py) — 모의데이터를 시험 자료로 쓴다.

모의데이터 파일끼리는 수치가 맞도록 만들어져 있다(65세 이상 인구 15,600명 등).
여기서 그 수치가 그대로 읽히는지 본다.
"""
import pytest

from app.services.doc_read import ReadError, read_document, to_text
from conftest import mock_file


def _tables(doc):
    return [b["rows"] for b in doc["blocks"] if b.get("rows")]


def _read(prefix):
    f = mock_file(prefix)
    return read_document(f.read_bytes(), f.name)


def test_hwpx_공고문은_배점표까지_표로_읽는다():
    doc = _read("01")
    assert doc["kind"] == "hwpx"
    first = _tables(doc)[0]
    assert first[0] == ["평가 항목", "세부 평가기준", "배점"]
    assert ["사업 필요성", "25"] == [first[1][0], first[1][2]]


def test_xlsx_병합_머리글을_채우고_날짜를_되돌린다():
    doc = _read("02")
    assert doc["kind"] == "xlsx"
    rows = _tables(doc)[0]
    # 병합된 머리글 '총인구(명)' 이 세 칸 모두에 채워진다
    head = next(r for r in rows if r[0] == "읍·면")
    assert head[1:4] == ["총인구(명)"] * 3
    # 날짜 서식은 날짜로, 정수는 정수로
    assert any(r[:2] == ["기준일", "2026-06-30"] for r in rows)
    total = next(r for r in rows if r[0] == "계")
    assert total[6] == "15600"          # 2026년 65세 이상 인구 합계


def test_확장자만_xls인_HTML표를_알아본다():
    doc = _read("03")
    assert doc["kind"] == "html표"
    assert "HTML 표" in doc["note"]       # 왜 그렇게 읽었는지 사람에게 말한다
    rows = _tables(doc)[0]
    assert rows[1][:3] == ["읍면명", "경로당수", "등록회원수"]


def test_docx_문단과_표를_함께_읽는다():
    doc = _read("04")
    assert doc["kind"] == "docx"
    assert _tables(doc)[0][0] == ["구분", "응답자(명)", "만족 이상(%)"]
    assert any(not b.get("rows") for b in doc["blocks"])   # 문단도 있다


def test_본문으로_펴면_표_글자가_남는다():
    text = to_text(_read("02"))
    assert "15600" in text and "가온읍" in text


def test_확장자를_믿지_않는다():
    # docx 내용에 .hwpx 이름을 붙여도 docx 로 읽는다
    f = mock_file("04")
    assert read_document(f.read_bytes(), "잘못된이름.hwpx")["kind"] == "docx"


@pytest.mark.parametrize("data, hint", [
    (b"", "빈 파일"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600, ""),   # 깨진 OLE — 어떤 이유든 말해야 한다
    (b"plain text, not a document", "읽을 수 없는 형식"),
])
def test_못_읽으면_이유를_말한다(data, hint):
    with pytest.raises(ReadError) as e:
        read_document(data, "x.bin")
    assert str(e.value).strip()
    assert hint in str(e.value)
