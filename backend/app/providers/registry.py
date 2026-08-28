# -*- coding: utf-8 -*-
"""설정으로 공급자를 선택하는 팩토리. LLM_PROVIDER 환경변수로 기본 모델을 고른다."""
import os
from .openai_provider import OpenAIProvider
from .claude_provider import ClaudeProvider
from .gemini_provider import GeminiProvider

_REGISTRY = {"openai": OpenAIProvider, "claude": ClaudeProvider, "gemini": GeminiProvider}

def get_provider(name: str | None = None):
    key = (name or os.getenv("LLM_PROVIDER", "openai")).lower()
    if key not in _REGISTRY:
        raise ValueError(f"알 수 없는 공급자: {key} (openai/claude/gemini 중 하나)")
    return _REGISTRY[key]()
