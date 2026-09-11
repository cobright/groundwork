# -*- coding: utf-8 -*-
"""Claude 어댑터.
- Claude Opus 4.7 이후는 온도를 기본값이 아닌 값으로 보내면 400 이다 → 한 번 빼고 다시 보낸다.
- Opus 5 는 생각이 기본으로 켜지고 `max_tokens` 가 생각+답을 함께 막는다 → 한도에 여유(base.HEADROOM).
- 답은 위치가 아니라 블록 종류(type == "text")로 모은다 — 앞에 생각 블록이 올 수 있다.
"""
from . import base
from .base import Message
from ..services import aiconfig

URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"


class ClaudeProvider:
    name = "claude"
    label = "Claude"

    def __init__(self, model: str | None = None, tier: str = "base"):
        self.tier = tier if tier in aiconfig.TIER_NAMES else "base"
        self.model = model or aiconfig.RECOMMENDED[self.name][self.tier]
        self.timeout = aiconfig.TIMEOUT[self.tier]
        self.key = aiconfig.value("ANTHROPIC_API_KEY")

    def _headers(self) -> dict:
        return {"x-api-key": self.key, "anthropic-version": API_VERSION}

    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        if not self.key:
            raise base.no_key(self.label)
        system = "\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": m.content} for m in messages if m.role in ("user", "assistant")]
        body = {"model": self.model, "max_tokens": base.output_limit(max_tokens, self.tier), "messages": turns}
        if system:
            body["system"] = system
        send_temp = base.sampling_ok(self.name, self.model)
        r = base.post(f"{URL}/messages", headers=self._headers(),
                      json={**body, "temperature": temperature} if send_temp else body, timeout=self.timeout)
        if send_temp and base.rejected_sampling(self.name, self.model, r):
            r = base.post(f"{URL}/messages", headers=self._headers(), json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise base.http_error(self.label, self.model, r)
        data = r.json()
        text = "".join(b.get("text", "") for b in (data.get("content") or [])
                       if isinstance(b, dict) and b.get("type") == "text")
        if not text.strip():
            raise base.empty_reply(self.label, self.model, data.get("stop_reason") or "")
        return text

    def list_models(self) -> list[dict]:
        if not self.key:
            raise base.no_key(self.label)
        out, after = [], None
        for _ in range(5):                      # 한 쪽에 1000개 — 사실상 한 번에 끝난다
            params = {"limit": 1000}
            if after:
                params["after_id"] = after
            r = base.get(f"{URL}/models", headers=self._headers(), params=params)
            if r.status_code >= 400:
                raise base.http_error(self.label, "", r)
            j = r.json()
            out += [{"id": m["id"], "label": m.get("display_name") or m["id"]}
                    for m in (j.get("data") or []) if isinstance(m, dict) and m.get("id")]
            if not j.get("has_more") or not j.get("last_id"):
                break
            after = j["last_id"]
        return out
