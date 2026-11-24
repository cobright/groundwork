# -*- coding: utf-8 -*-
"""로컬 서버를 다른 웹사이트로부터 지킨다.

이 앱은 이 PC 안(127.0.0.1)에서만 돌고 로그인이 없다. 그래서 '같은 PC 의 브라우저'가 곧 사용자다.
그런데 사용자가 프로그램을 켜 둔 채 **다른 웹사이트**를 열면, 그 사이트의 스크립트도 같은 브라우저에서
127.0.0.1:8000 으로 요청을 보낼 수 있다. 두 가지를 막는다.

1) 다른 사이트발 쓰기 (CSRF)
   JSON 을 받는 API 는 FastAPI 가 Content-Type 을 따져 이미 막지만, 파일 업로드 API 는 원시 바이트를
   받으므로 `text/plain` 요청이 그대로 들어왔다(2026-11-24 시험에서 201 — 업무에 가짜 자료를 심을 수 있었다).
   → 쓰기 요청(POST·PUT·PATCH·DELETE)은 브라우저가 붙이는 출처 표시를 본다:
     `Sec-Fetch-Site: cross-site` 이거나, `Origin` 이 이 PC 주소가 아니면 거절한다.
     Origin 이 아예 없는 요청(curl·스크립트 등 브라우저 밖)은 받는다 — 그쪽은 이미 이 PC 의 권한이다.

2) 남의 주소로 들어오는 요청 (DNS 리바인딩)
   외부 도메인을 127.0.0.1 로 바꿔 가리키게 하면 브라우저는 '같은 사이트'로 여겨 응답까지 읽게 해 준다.
   → Host 가 이 PC 주소(127.0.0.1·localhost)가 아니면 거절한다. 그러면 읽기도 막힌다.

포트는 따지지 않는다(개발 서버 5173 → 8000 프록시, 포터블 8000 모두 같은 PC).
LAN 의 다른 PC 에서 접속하는 쓰임은 없다(원칙 3·4 — 서버를 두지 않는다). 생기면 여기를 먼저 고친다.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _hostname(host_header: str) -> str:
    # "127.0.0.1:8000" → "127.0.0.1". (IPv6 는 쓰지 않는다 — 실행 경로가 모두 127.0.0.1 에 묶여 있다)
    return host_header.rsplit(":", 1)[0].strip().lower() if host_header else ""


def _origin_is_local(origin: str) -> bool:
    try:
        return (urlsplit(origin).hostname or "").lower() in LOCAL_HOSTS
    except ValueError:
        return False


async def _reject(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class LocalOnlyMiddleware:
    """위의 두 규칙을 모든 HTTP 요청(정적 파일 포함)에 건다."""

    def __init__(self, app, allowed_hosts: set[str] | None = None):
        self.app = app
        self.allowed_hosts = allowed_hosts or LOCAL_HOSTS

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

        if _hostname(headers.get("host", "")) not in self.allowed_hosts:
            return await _reject(send, 400, "이 프로그램은 이 PC 의 주소(http://127.0.0.1:8000)로만 열 수 있습니다.")

        if scope.get("method", "GET").upper() in WRITE_METHODS:
            site = headers.get("sec-fetch-site", "")
            origin = headers.get("origin")
            cross = site == "cross-site" or (origin is not None and not _origin_is_local(origin))
            if cross:
                return await _reject(send, 403, "다른 웹사이트에서 온 요청이라 거절했습니다. "
                                                "이 프로그램 화면에서 직접 해 주세요.")
        return await self.app(scope, receive, send)
