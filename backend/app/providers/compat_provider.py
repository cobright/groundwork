# -*- coding: utf-8 -*-
"""OpenAI 호환 서버 어댑터 — 회사가 아니라 **주소**를 고르는 공급자.

왜 OpenAI 어댑터를 돌려 쓰지 않는가:
  행정안전부 AI 공통기반이 지원하는 모델(엑사원·솔라·젬마·라마·GPT-OSS 등)은 대개
  OpenAI 호환 `/v1/chat/completions` 를 내준다. 그래서 OpenAI 어댑터의 주소만 바꾸면
  동작은 한다. 그러나 그러면 초고·검토 결과에 쓴 모델로 **'OpenAI'** 가 찍힌다.
  실패해도 다른 회사로 몰래 넘기지 않는 것과 같은 이유로, 이름이 거짓이 되게 둘 수 없다.

OpenAI 어댑터와 실제로 다른 네 가지:
  ① 주소가 설정값이다(`COMPAT_BASE_URL`). 없으면 무엇을 해야 하는지 말하고 멈춘다.
  ② 한도를 `max_tokens` 로 보낸다 — vLLM·Ollama 류는 `max_completion_tokens` 를 모른다.
  ③ **키가 없을 수 있다**(기관 내부망 서버는 인증이 없는 경우가 있다). 없으면 헤더를 뺀다.
  ④ 모델 목록을 이름으로 거르지 않는다. 기관이 올린 이름은 `gpt-`·`o1` 꼴이 아니다.
"""
from . import base
from .base import Message
from ..services import aiconfig

# 글쓰기에 못 쓰는 것만 이름으로 거른다(임베딩 모델이 목록에 섞여 온다).
_SKIP = ("embedding", "embed", "rerank", "tts", "whisper", "stt", "moderation", "clip")


class CompatProvider:
    name = "compat"
    label = "호환 서버"

    def __init__(self, model: str | None = None, tier: str = "base"):
        self.tier = tier if tier in aiconfig.TIER_NAMES else "base"
        # 추천값이 없다(기관마다 다르다) → 비어 있으면 complete() 가 할 일을 말해 준다.
        self.model = model or aiconfig.value("COMPAT_MODEL")
        self.timeout = aiconfig.TIMEOUT[self.tier]
        self.key = aiconfig.value("COMPAT_API_KEY")
        self.url = aiconfig.base_url("compat")

    def _headers(self) -> dict:
        # 키가 없으면 헤더를 아예 보내지 않는다 — 빈 Bearer 를 401 로 되돌려주는 서버가 있다.
        return {"Authorization": f"Bearer {self.key}"} if self.key else {}

    def _ready(self) -> None:
        if not self.url:
            raise base.no_base(self.label)
        if not self.model:
            raise RuntimeError(
                "호환 서버는 모델 이름을 직접 적어야 합니다(추천값이 없습니다). "
                "설정의 ‘목록’으로 그 서버가 가진 모델을 불러와 고르세요.")

    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        self._ready()
        body = {"model": self.model, "max_tokens": base.output_limit(max_tokens, self.tier),
                "messages": [{"role": m.role, "content": m.content} for m in messages]}
        send_temp = base.sampling_ok(self.name, self.model)
        r = base.post(f"{self.url}/chat/completions", headers=self._headers(),
                      json={**body, "temperature": temperature} if send_temp else body,
                      timeout=self.timeout)
        if send_temp and base.rejected_sampling(self.name, self.model, r):
            r = base.post(f"{self.url}/chat/completions", headers=self._headers(), json=body,
                          timeout=self.timeout)
        if r.status_code >= 400:
            raise base.http_error(self.label, self.model, r)
        choice = (r.json().get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        if not text.strip():
            raise base.empty_reply(self.label, self.model, choice.get("finish_reason") or "")
        return text

    def list_models(self) -> list[dict]:
        if not self.url:
            raise base.no_base(self.label)
        r = base.get(f"{self.url}/models", headers=self._headers())
        if r.status_code >= 400:
            raise base.http_error(self.label, "", r)
        rows = [m for m in (r.json().get("data") or []) if isinstance(m, dict) and m.get("id")]
        rows = [m for m in rows if not any(s in m["id"].lower() for s in _SKIP)]
        rows.sort(key=lambda m: m.get("created") or 0, reverse=True)
        return [{"id": m["id"], "label": m["id"]} for m in rows]
