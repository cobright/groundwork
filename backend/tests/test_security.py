# -*- coding: utf-8 -*-
"""다른 웹사이트로부터 로컬 서버 지키기(app/security.py).

2026-11-24 시험: 다른 출처에서 text/plain 으로 보낸 파일 업로드가 201 로 들어왔다.
여기서는 그 공격이 막히고, 정상 사용(같은 PC 화면·개발 서버·브라우저 밖 스크립트)은 막히지 않는지 본다.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import main

EVIL = "https://evil.example"


def _upload(client, pid, headers):
    return client.post(f"/api/projects/{pid}/resources/upload?filename=a.html&name=x",
                       content="<table><tr><td>가짜</td></tr></table>".encode(), headers=headers)


def test_다른_사이트발_업로드는_거절한다(client, project):
    r = _upload(client, project, {"Origin": EVIL, "Content-Type": "text/plain"})
    assert r.status_code == 403
    assert "다른 웹사이트" in r.json()["detail"]
    assert client.get(f"/api/projects/{project}/resources").json() == []    # 아무것도 심기지 않았다


def test_출처를_숨겨도_브라우저의_사이트_표시로_거절한다(client, project):
    r = _upload(client, project, {"Sec-Fetch-Site": "cross-site", "Content-Type": "text/plain"})
    assert r.status_code == 403


@pytest.mark.parametrize("origin", ["null", "http://127.0.0.1.evil.example", "http://localhost.evil.example:8000"])
def test_이_PC처럼_보이는_가짜_출처도_거절한다(client, project, origin):
    assert _upload(client, project, {"Origin": origin}).status_code == 403


@pytest.mark.parametrize("headers", [
    {"Origin": "http://127.0.0.1:8000", "Sec-Fetch-Site": "same-origin"},     # 포터블·run.py 화면
    {"Origin": "http://localhost:5173", "Sec-Fetch-Site": "same-origin"},     # 개발 서버(프록시)
    {},                                                                        # 브라우저 밖(curl·스크립트)
])
def test_정상_사용은_막지_않는다(client, project, headers):
    assert _upload(client, project, headers).status_code == 201


def test_다른_사이트도_읽기는_서버가_막지_않는다_읽기는_CORS가_막는다(client, project):
    # 같은 주소(Host)로 온 GET 은 통과한다. 응답을 남의 스크립트가 읽는 것은 브라우저(CORS)가 막는다.
    r = client.get(f"/api/projects/{project}", headers={"Origin": EVIL})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.nip.io", "testserver"])
def test_남의_주소로_들어온_요청은_읽기도_막는다(host):
    c = TestClient(main.app, base_url=f"http://{host}")
    r = c.get("/api/health")
    assert r.status_code == 400
    assert "127.0.0.1" in r.json()["detail"]


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:5173", "LOCALHOST"])
def test_이_PC_주소는_받는다(host):
    c = TestClient(main.app, base_url=f"http://{host}")
    assert c.get("/api/health").status_code == 200
