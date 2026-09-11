# -*- coding: utf-8 -*-
"""OpenAI 어댑터.
- 한도는 `max_completion_tokens` 로 보낸다. 추론 모델은 `max_tokens` 를 받지 않고,
  예전 모델도 이 이름을 받는다.
- 온도를 거부하는 모델이면 한 번만 빼고 다시 보낸다(base.rejected_sampling).
"""
import re

from . import base
from .base import Message
from ..services import aiconfig

URL = "https://api.openai.com/v1"
# 목록에서 글쓰기에 못 쓰는 모델을 거른다(이름으로만 알 수 있다).
_SKIP = ("embedding", "tts", "whisper", "dall-e", "image", "audio", "realtime",
         "transcribe", "moderation", "search", "sora")


class OpenAIProvider:
    name = "openai"
    label = "OpenAI"

    def __init__(self, model: str | None = None, tier: str = "base"):
        self.tier = tier if tier in aiconfig.TIER_NAMES else "base"
        self.model = model or aiconfig.RECOMMENDED[self.name][self.tier]
        self.timeout = aiconfig.TIMEOUT[self.tier]
        self.key = aiconfig.value("OPENAI_API_KEY")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.key}"}

    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        if not self.key:
            raise base.no_key(self.label)
        body = {"model": self.model, "max_completion_tokens": base.output_limit(max_tokens, self.tier),
                "messages": [{"role": m.role, "content": m.content} for m in messages]}
        send_temp = base.sampling_ok(self.name, self.model)
        r = base.post(f"{URL}/chat/completions", headers=self._headers(),
                      json={**body, "temperature": temperature} if send_temp else body, timeout=self.timeout)
        if send_temp and base.rejected_sampling(self.name, self.model, r):
            r = base.post(f"{URL}/chat/completions", headers=self._headers(), json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise base.http_error(self.label, self.model, r)
        choice = (r.json().get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        if not text.strip():
            raise base.empty_reply(self.label, self.model, choice.get("finish_reason") or "")
        return text

    def list_models(self) -> list[dict]:
        if not self.key:
            raise base.no_key(self.label)
        r = base.get(f"{URL}/models", headers=self._headers())
        if r.status_code >= 400:
            raise base.http_error(self.label, "", r)
        rows = [m for m in (r.json().get("data") or []) if isinstance(m, dict) and m.get("id")]
        rows = [m for m in rows if re.match(r"^(gpt-|o\d|chatgpt-)", m["id"])
                and not any(s in m["id"] for s in _SKIP)]
        rows.sort(key=lambda m: m.get("created") or 0, reverse=True)
        return [{"id": m["id"], "label": m["id"]} for m in rows]
