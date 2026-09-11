# -*- coding: utf-8 -*-
"""LLM 공급자 공통 인터페이스 + 어댑터 셋이 함께 쓰는 요청·오류 처리.
모든 어댑터는 complete() 하나를 구현한다. 하네스/에이전트는 이 인터페이스만 알면 되고,
실제 모델(OpenAI/Claude/Gemini)은 설정의 등급(services/aiconfig.py)으로 갈아끼운다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass
class Message:
    role: str   # "system" | "user" | "assistant"
    content: str


class LLMProvider(Protocol):
    name: str
    label: str
    model: str
    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        ...
    def list_models(self) -> list[dict]:
        ...


# 생각(추론) 토큰이 출력 한도를 함께 쓰는 모델이 늘었다(Claude Opus 5 · Gemini 3.x · GPT-5.x).
# 호출부의 max_tokens 는 '보이는 답'의 분량으로 정한 값이라, 그대로 보내면 생각만 하다가
# 빈 답으로 끝날 수 있다(연결 시험의 20 은 거의 확실히 그렇다). 그래서 보낼 때 여유를 더한다.
# 쓰지 않은 한도는 청구되지 않는다. 정밀은 생각이 길어 더 둔다.
HEADROOM = {"fast": 4000, "base": 4000, "deep": 8000}


def output_limit(max_tokens: int, tier: str) -> int:
    return int(max_tokens) + HEADROOM.get(tier, 4000)


# 온도(temperature)를 거부하는 모델이 있다(Claude Opus 4.7 이후, GPT-5 계열 일부).
# 모델 이름으로 미리 가르면 새 모델이 나올 때마다 틀린다. 그래서 한 번 거부당하면
# 프로그램이 켜져 있는 동안 기억하고, 그 모델에는 더 보내지 않는다.
_NO_SAMPLING: set[tuple[str, str]] = set()


def sampling_ok(provider: str, model: str) -> bool:
    return (provider, model) not in _NO_SAMPLING


def rejected_sampling(provider: str, model: str, r: httpx.Response) -> bool:
    """400 이 온도 때문이면 기억해 두고 True — 호출한 쪽이 온도를 빼고 한 번 더 보낸다."""
    if r.status_code == 400 and "temperature" in (r.text or "").lower():
        _NO_SAMPLING.add((provider, model))
        return True
    return False


def _call(method, url: str, **kw) -> httpx.Response:
    """망 오류를 담당자가 할 일로 옮긴다. 키가 틀린 것과 망이 막힌 것은 할 일이 전혀 다르다."""
    timeout = kw.get("timeout", 30)
    try:
        return method(url, **kw)
    except httpx.TimeoutException:
        raise RuntimeError(f"AI 서버가 {int(timeout)}초 안에 답하지 않았습니다. "
                           "잠시 뒤 다시 하거나, 설정에서 더 빠른 모델을 고르세요.")
    except httpx.TransportError as e:
        raise RuntimeError(f"AI 서버에 닿지 못했습니다 — 망이나 방화벽을 확인하세요. ({e})")


def post(url: str, *, headers: dict, json: dict, timeout: float) -> httpx.Response:
    return _call(httpx.post, url, headers=headers, json=json, timeout=timeout)


def get(url: str, *, headers: dict, params: dict | None = None, timeout: float = 30) -> httpx.Response:
    return _call(httpx.get, url, headers=headers, params=params, timeout=timeout)


def _detail(r: httpx.Response) -> str:
    try:
        j = r.json()
        e = j.get("error") if isinstance(j, dict) else None
        if isinstance(e, dict):
            return str(e.get("message") or "")[:300]
        if isinstance(e, str):
            return e[:300]
    except Exception:                           # noqa: BLE001 — 본문이 JSON 이 아니어도 말은 해 준다
        pass
    return (r.text or "")[:200]


def http_error(label: str, model: str, r: httpx.Response) -> RuntimeError:
    """상태 코드를 담당자가 할 일로 옮긴다.
    예전엔 raise_for_status() 의 영문 메시지가 그대로 나갔고, Gemini 는 주소에 키가 들어 있어
    화면 오류에 키가 섞였다. 이제 키는 헤더로만 보내고, 주소를 오류에 싣지 않는다."""
    s = r.status_code
    if s in (401, 403):
        msg = f"{label} 키가 맞지 않거나 이 모델을 쓸 권한이 없습니다"
    elif s == 404:
        msg = (f"{label} 에서 모델({model})을 찾지 못했습니다 — 설정의 '목록'으로 지금 쓸 수 있는 모델을 고르세요"
               if model else f"{label} 주소를 찾지 못했습니다")
    elif s == 429:
        msg = f"{label} 사용 한도(요청 수·요금)를 넘었습니다"
    else:
        msg = f"{label} 서버 오류({s})"
    d = _detail(r)
    return RuntimeError(f"{msg}. [{d}]" if d else f"{msg}.")


def empty_reply(label: str, model: str, why: str = "") -> RuntimeError:
    tail = f" (사유: {why})" if why else ""
    return RuntimeError(f"{label} 모델({model})이 빈 답을 보냈습니다{tail} — "
                        "출력 한도가 모자랐거나 응답이 막혔을 수 있습니다.")


def no_key(label: str) -> RuntimeError:
    return RuntimeError(f"{label} 키가 설정되지 않았습니다. 화면 위쪽 ‘설정’에서 키를 넣어 주세요.")
