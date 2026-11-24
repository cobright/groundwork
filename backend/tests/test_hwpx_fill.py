# -*- coding: utf-8 -*-
"""한글(HWPX) 양식에 최종본 채우기 — 양식의 구조는 그대로, 내용만 사람이 확정한 본문으로.

가상 양식은 hwpx_sample.make_form() 이 만든다(실제 기관 양식은 공개 저장소에 넣을 수 없다).
"""
import io
import zipfile

import defusedxml.ElementTree as ET
import pytest

from app.services.hwpx_fill import HP, fill_form, inspect_form, parse_body
from hwpx_sample import make_form

P = "{%s}" % HP


def _text(p):
    # 탭 뒤 꼬리(쪽번호)까지 읽는다 — 목차의 쪽번호가 비워졌는지 봐야 한다
    return "".join("".join(t.itertext()) for t in p.iter(P + "t"))


def _body_start(root):
    """첫 장 제목 표의 자리. (제목 글자가 든 첫 표는 표지 제목 상자라 기준이 될 수 없다)"""
    tops = root.findall(f"./{P}p")
    return tops, next(i for i, p in enumerate(tops) if _has_table(p) and _text(p).startswith("Ⅰ"))


def _has_table(p):
    return p.find(f".//{P}tbl") is not None


@pytest.fixture
def form():
    return make_form()


@pytest.fixture
def filled_project(client, project):
    client.put(f"/api/projects/{project}", json={"name": "스마트 경로당 계획"})
    client.put(f"/api/projects/{project}/outline", json={"nodes": [
        {"uid": "a", "sort": 0, "title": "추진 배경"},
        {"uid": "a1", "parent_uid": "a", "sort": 1, "title": "현황"},
        {"uid": "a2", "parent_uid": "a", "sort": 2, "title": "문제점"},
        {"uid": "b", "sort": 3, "title": "추진 계획"},
        {"uid": "c", "sort": 4, "title": "기대 효과"},
    ]})
    for uid, body in (("a1", "○ 인구 15,600명\n- 읍면별 차이\n[확인 필요: 출처]"),
                      ("b", "□ 1단계 설계\n○ 세부 일정")):
        client.put(f"/api/projects/{project}/nodes/{uid}/draft", json={"body": body})
    client.put(f"/api/projects/{project}/nodes/a2/draft", json={"body": ""})
    from app import db
    with db.connect() as c:                       # 반영하지 않은 AI 제안은 양식에 들어가면 안 된다
        c.execute("UPDATE drafts SET ai_suggestion='반영 안 한 AI 문장' WHERE node_uid='a1'")
    return project


def _fill(pid, form, **kw):
    data, name = fill_form(pid, form, **kw)
    z = zipfile.ZipFile(io.BytesIO(data))
    root = ET.fromstring(z.read("Contents/section0.xml"))
    return z, root, name


def test_양식을_미리_살펴_수준과_장_수를_알려준다(form):
    info = inspect_form(form)
    assert info["supported"] is True and info["reason"] == ""
    assert info["levels"] == [1, 2, 3, 4] and info["chapters"] == 2
    assert info["marks"] == {1: "□", 2: "○", 3: "―", 4: "※"}


def test_보고서_양식이_아니면_이유를_말한다():
    from conftest import mock_file
    info = inspect_form(mock_file("01").read_bytes())          # 공고문 hwpx — 장 제목 표가 없다
    assert info["supported"] is False and "찾지 못했습니다" in info["reason"]
    assert inspect_form(b"not a zip")["supported"] is False


def test_표지_날짜_기관명을_채운다(filled_project, form):
    _, root, name = _fill(filled_project, form, org="가온군")
    texts = [_text(p).strip() for p in root.iter(P + "p") if not _has_table(p)]
    assert texts.count("스마트 경로당 계획") == 2              # 제목 상자 + '제 목' 자리
    assert "부제 둘째 줄" not in texts                          # 두 줄 제목의 옛 줄은 비운다
    assert "보고서 양식(제목)" not in texts and "2026. 1. 1." not in texts
    assert "가온군" in texts and name == "스마트 경로당 계획.hwpx"


def test_목차는_우리_장으로_바꾸고_꼬리_안내는_남긴다(filled_project, form):
    _, root, _ = _fill(filled_project, form)
    toc = next(s for s in root.iter(P + "subList") if any(_text(q).strip() == "목 차" for q in s))
    lines = [_text(q).strip() for q in toc]
    # 쪽번호는 비운다(실제 쪽수를 모른다). 옛 하위 항목은 걷어내고, [붙 임] 꼬리는 쪽번호까지 그대로 둔다.
    assert lines == ["목 차", "Ⅰ. 추진 배경", "Ⅱ. 추진 계획", "Ⅲ. 기대 효과", "[붙 임] 별지 서식 안내9"]


def test_본문은_장_표와_개조식으로_양식_서식을_따라_쌓는다(filled_project, form):
    _, root, _ = _fill(filled_project, form)
    tops, start = _body_start(root)
    assert _text(tops[start - 1]).strip() == "스마트 경로당 계획"      # 바로 앞은 '제 목' 자리
    body = [("표 " if _has_table(p) else "") + _text(p) for p in tops[start:]]
    assert body == [
        "표 Ⅰ 추진 배경",
        "□ 현황",
        "  ○ 인구 15,600명",
        "   ― 읍면별 차이",                    # '-' 로 쓴 줄도 양식의 3수준 기호(―)로
        "     ※ [확인 필요: 출처]",            # [확인 필요] 는 ※ 수준으로 드러난다
        "□ 문제점",
        "  ○ (본문 없음)",
        "표 Ⅱ 추진 계획",
        "□ 1단계 설계",
        "  ○ 세부 일정",
        "표 Ⅲ 기대 효과",                     # 양식엔 장이 2개뿐 — 표를 복제해 늘린다
        "□ (본문 없음)",
    ]
    assert not any("옛" in t for t in body)
    assert not any("반영 안 한 AI 문장" in t for t in body)


def test_한글이_깨지지_않게_손댄_문단의_줄바꿈_캐시를_지운다(filled_project, form):
    _, root, _ = _fill(filled_project, form)
    tops, start = _body_start(root)
    for p in tops[start:]:
        assert p.find(f".//{P}linesegarray") is None, _text(p)


def test_쪽번호_재시작은_첫_장에만_남는다(filled_project, form):
    _, root, _ = _fill(filled_project, form, page_break=True)
    chapters = [p for p in root.findall(f"./{P}p") if _has_table(p) and _text(p)[:1] in "ⅠⅡⅢ"
                and "." not in _text(p)]
    assert [p.find(f".//{P}newNum") is not None for p in chapters] == [True, False, False]
    assert [p.get("pageBreak") for p in chapters[1:]] == ["1", "1"]


def test_다시_묶을_때_mimetype이_첫_항목이고_무압축이다(filled_project, form):
    z, _, _ = _fill(filled_project, form)
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert z.testzip() is None
    assert z.namelist() == zipfile.ZipFile(io.BytesIO(form)).namelist()   # 양식의 항목을 그대로
    assert "Ⅲ. 기대 효과" in z.read("Preview/PrvText.txt").decode("utf-8")


def test_API로_양식을_올리고_채워_내려받는다(client, filled_project, form):
    r = client.post("/api/forms", params={"filename": "가상 양식.hwpx", "name": "가상 양식"}, content=form)
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    r = client.get(f"/api/projects/{filled_project}/export.hwpx", params={"form_id": fid, "org": "가온군"})
    assert r.status_code == 200, r.text
    assert zipfile.ZipFile(io.BytesIO(r.content)).infolist()[0].filename == "mimetype"
    assert client.get(f"/api/projects/{filled_project}/export.hwpx", params={"form_id": 999}).status_code == 404


def test_본문_줄머리로_수준을_가른다():
    assert parse_body("□ 큰 항목\n○ 내용\nㅇ 내용2\n- 세부\n· 점\n※ 주석\n그냥 문장\n[추정] 짐작\n\n") == [
        (1, "큰 항목"), (2, "내용"), (2, "내용2"), (3, "세부"), (3, "점"), (4, "주석"),
        (2, "그냥 문장"), (4, "[추정] 짐작")]
