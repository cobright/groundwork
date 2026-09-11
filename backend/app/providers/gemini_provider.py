# -*- coding: utf-8 -*-
"""Gemini 어댑터.
- 키는 주소(?key=)가 아니라 헤더(x-goog-api-key)로 보낸다 — 주소에 있으면 오류 문구에 키가 섞인다.
- 3.x 모델은 생각 토큰이 maxOutputTokens 를 함께 쓴다 → 한도에 여유(base.HEADROOM).
  답이 비면 KeyError 대신 사유(finishReason/blockReason)를 담아 알린다.
"""
from . import base
from .base import Message
from ..services import aiconfig

URL = "https://generativelanguage.googleapis.com/v1beta"
_SKIP = ("embedding", "image", "tts", "audio", "live", "robotics", "veo", "imagen")


class GeminiProvider:
    name = "gemini"
    label = "Gemini"

    def __init__(self, model: str | None = None, tier: str = "base"):
        self.tier = tier if tier in aiconfig.TIER_NAMES else "base"
        self.model = (model or aiconfig.RECOMMENDED[self.name][self.tier]).removeprefix("models/")
        self.timeout = aiconfig.TIMEOUT[self.tier]
        self.key = aiconfig.value("GEMINI_API_KEY")

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.key}

    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        if not self.key:
            raise base.no_key(self.label)
        contents = [{"role": ("user" if m.role != "assistant" else "model"),
                     "parts": [{"text": m.content}]} for m in messages if m.role != "system"]
        sys = [m.content for m in messages if m.role == "system"]
        gen = {"maxOutputTokens": base.output_limit(max_tokens, self.tier)}
        body = {"contents": contents, "generationConfig": gen}
        if sys:
            body["systemInstruction"] = {"parts": [{"text": "\n".join(sys)}]}
        url = f"{URL}/models/{self.model}:generateContent"
        send_temp = base.sampling_ok(self.name, self.model)
        r = base.post(url, headers=self._headers(), timeout=self.timeout,
                      json={**body, "generationConfig": {**gen, "temperature": temperature}} if send_temp else body)
        if send_temp and base.rejected_sampling(self.name, self.model, r):
            r = base.post(url, headers=self._headers(), json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise base.http_error(self.label, self.model, r)
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            raise base.empty_reply(self.label, self.model,
                                   (data.get("promptFeedback") or {}).get("blockReason") or "")
        c = cands[0]
        parts = (c.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        if not text.strip():
            raise base.empty_reply(self.label, self.model, c.get("finishReason") or "")
        return text

    def list_models(self) -> list[dict]:
        if not self.key:
            raise base.no_key(self.label)
        out, token = [], None
        for _ in range(5):
            params = {"pageSize": 1000}
            if token:
                params["pageToken"] = token
            r = base.get(f"{URL}/models", headers=self._headers(), params=params)
            if r.status_code >= 400:
                raise base.http_error(self.label, "", r)
            j = r.json()
            for m in j.get("models") or []:
                mid = str(m.get("name") or "").removeprefix("models/")
                if not mid.startswith("gemini-") or any(s in mid for s in _SKIP):
                    continue
                if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                    continue
                out.append({"id": mid, "label": m.get("displayName") or mid})
            token = j.get("nextPageToken")
            if not token:
                break
        return out
