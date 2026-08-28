# -*- coding: utf-8 -*-
"""LLM 공급자 공통 인터페이스.
모든 어댑터는 complete() 하나를 구현한다. 하네스/에이전트는 이 인터페이스만 알면 되고,
실제 모델(OpenAI/Claude/Gemini)은 환경변수와 설정으로 갈아끼운다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Message:
    role: str   # "system" | "user" | "assistant"
    content: str


class LLMProvider(Protocol):
    name: str
    def complete(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        ...
