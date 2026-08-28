# -*- coding: utf-8 -*-
import os
import httpx
from .base import Message

class GeminiProvider:
    name = "gemini"
    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
        self.key = os.getenv("GEMINI_API_KEY", "")
    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY 가 설정되지 않았습니다 (.env 확인).")
        contents = [{"role": ("user" if m.role != "assistant" else "model"),
                     "parts": [{"text": m.content}]} for m in messages if m.role != "system"]
        sys = [m.content for m in messages if m.role == "system"]
        body = {"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if sys:
            body["systemInstruction"] = {"parts": [{"text": "\n".join(sys)}]}
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}",
            json=body, timeout=60,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
