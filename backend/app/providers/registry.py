# -*- coding: utf-8 -*-
"""일(task) → 등급 → (회사, 모델) 로 어댑터를 만든다.

호출부는 **무슨 일인지만** 말한다(`task="draft_plan"`). 어느 등급·회사·모델을 쓸지는
services/aiconfig.py 의 TASKS·resolve() 가 정한다 — 배정이 호출부에 흩어지면 설정 화면의 표와 어긋난다.
실패해도 다른 등급·회사로 몰래 넘기지 않는다: 결과에 찍히는 모델 이름이 거짓말이 되기 때문이다.
"""
from .openai_provider import OpenAIProvider
from .claude_provider import ClaudeProvider
from .gemini_provider import GeminiProvider
from .compat_provider import CompatProvider
from ..services import aiconfig

_REGISTRY = {"openai": OpenAIProvider, "claude": ClaudeProvider, "gemini": GeminiProvider,
             "compat": CompatProvider}


def build(provider: str, model: str | None = None, tier: str = "base"):
    """회사·모델·등급을 직접 정해 만든다(설정 화면의 '저장 전 시험'·모델 목록이 쓴다)."""
    key = (provider or "").lower()
    if key not in _REGISTRY:
        raise ValueError(f"알 수 없는 공급자: {key} (openai/claude/gemini/compat 중 하나)")
    return _REGISTRY[key](model=model or None, tier=tier)


def get_provider(name: str | None = None, task: str | None = None):
    """name: 작업 화면에서 고른 회사(비우면 설정대로). task: 무슨 일인지(비우면 기본 등급)."""
    tier = aiconfig.task_tier(task)
    r = aiconfig.resolve(tier, override=name)
    return build(r["provider"], r["model"], tier)
