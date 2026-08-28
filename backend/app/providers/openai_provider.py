# -*- coding: utf-8 -*-
import os
import httpx
from .base import Message

class OpenAIProvider:
    name = "openai"
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.key = os.getenv("OPENAI_API_KEY", "")
    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        if not self.key:
            raise RuntimeError("OPENAI_API_KEY 가 설정되지 않았습니다 (.env 확인).")
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                  "messages": [{"role": m.role, "content": m.content} for m in messages]},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
