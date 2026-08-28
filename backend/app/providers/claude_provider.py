# -*- coding: utf-8 -*-
import os
import httpx
from .base import Message

class ClaudeProvider:
    name = "claude"
    def __init__(self, model: str | None = None):
        # 모델 문자열은 설정으로 교체 가능. 기본값은 예시일 뿐이므로 .env 에서 지정하세요.
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        self.key = os.getenv("ANTHROPIC_API_KEY", "")
    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        if not self.key:
            raise RuntimeError("ANTHROPIC_API_KEY 가 설정되지 않았습니다 (.env 확인).")
        system = "\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": m.content} for m in messages if m.role in ("user", "assistant")]
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
            json={"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                  "system": system, "messages": turns},
            timeout=60,
        )
        r.raise_for_status()
        parts = [b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text"]
        return "".join(parts)
