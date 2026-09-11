# -*- coding: utf-8 -*-
"""설정 화면이 쓰는 입구 — AI 연결과 백업.

왜 화면에 내는가(원칙 4):
  지금까지 AI 키를 바꾸려면 `.env` 파일을 찾아 열고 고치고 프로그램을 껐다 켜야 했다.
  담당자에게는 세 단계가 각각 벽이다. 여기서는 저장하면 바로 반영된다.

**연결 시험을 반드시 함께 둔다.** 키를 넣었는데 되는지 안 되는지 모르는 상태가 가장 나쁘다
(방화벽이 막는 경우가 실제로 있다 — 그때 '키가 틀렸나'를 헤매게 된다).

등급별 모델(v0.26):
  등급(빠름·기본·정밀)마다 회사와 모델을 고른다. 시험은 **저장 전 값으로도** 할 수 있다 —
  목록에서 고르고, 시험해 보고, 되면 저장하는 순서가 자연스럽다.
  모델 목록은 그때그때 각 회사에서 불러온다. 이름은 몇 달이면 바뀌므로 저장해 두지 않는다.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import list_backups
from ..providers.base import Message
from ..providers.registry import build
from ..services import aiconfig

router = APIRouter(prefix="/api", tags=["setup"])


@router.get("/ai/config")
def get_ai_config():
    """현재 설정. **키 원문은 절대 돌려주지 않는다**(끝 4자리만)."""
    return aiconfig.snapshot()


class TierIn(BaseModel):
    provider: str | None = None   # None=그대로, ""=화면 값 지움(빠름·정밀은 '기본과 같게')
    model: str | None = None      # None=그대로, ""=화면 값 지움(추천값을 쓴다)


class AiConfigIn(BaseModel):
    tiers: dict[str, TierIn] = {}
    keys: dict[str, str | None] = {}   # None=그대로, ""=화면 설정 지움(.env 로 되돌림)


@router.put("/ai/config")
def put_ai_config(body: AiConfigIn):
    try:
        aiconfig.apply({k: v.model_dump() for k, v in body.tiers.items()}, body.keys)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return aiconfig.snapshot()


class TestIn(BaseModel):
    tier: str = "base"
    provider: str | None = None   # 화면에 고른 채 저장 전인 회사. None=저장된 설정, ""=기본 등급을 따름
    model: str | None = None      # 비우면 그 회사·등급의 추천값


@router.post("/ai/test")
def test_ai(body: TestIn):
    """실제로 한 번 불러 본다. 짧게 묻고 짧게 받는다(비용도 시간도 아끼려고).

    실패는 502 로 올리되 **왜 실패했는지 그대로** 담는다 — 키가 틀린 것과 망이 막힌 것은
    담당자가 해야 할 일이 전혀 다르다.
    """
    if body.tier not in aiconfig.TIER_NAMES:
        raise HTTPException(400, f"알 수 없는 등급: {body.tier}")
    try:
        if body.provider is None or body.provider == "":
            r = aiconfig.resolve(body.tier if body.provider is None else "base")
            provider = build(r["provider"], r["model"], body.tier)
        else:
            name = body.provider.strip().lower()
            model = (body.model or "").strip()
            if not model and name in aiconfig.RECOMMENDED:     # 비운 채 저장하면 쓰일 모델로 시험한다
                model = aiconfig.model_if_blank(name, body.tier)
            provider = build(name, model or None, body.tier)
    except ValueError as e:
        raise HTTPException(400, str(e))
    t0 = time.time()
    try:
        reply = provider.complete(
            [Message("system", "한국어로 아주 짧게 답하십시오."),
             Message("user", "연결 확인. '확인'이라고만 답하세요.")],
            temperature=0, max_tokens=20)
    except Exception as e:                      # noqa: BLE001 — 사람이 읽을 말로 그대로 올린다
        raise HTTPException(502, f"연결 실패: {e}")
    return {"ok": True, "tier": body.tier, "provider": provider.name, "label": provider.label,
            "model": provider.model, "seconds": round(time.time() - t0, 1),
            "reply": (reply or "").strip()[:80]}


@router.get("/ai/models")
def list_ai_models(provider: str):
    """그 회사가 지금 제공하는 글쓰기 모델 목록. 저장하지 않는다(이름은 몇 달이면 바뀐다)."""
    try:
        p = build(provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not p.key:
        raise HTTPException(400, f"{p.label} 키가 없습니다. 아래 'API 키'에서 키를 넣고 저장한 뒤 불러오세요.")
    try:
        models = p.list_models()
    except Exception as e:                      # noqa: BLE001
        raise HTTPException(502, f"{p.label} 모델 목록을 불러오지 못했습니다: {e}")
    return {"provider": p.name, "models": models}


@router.get("/backups")
def get_backups():
    """자동 백업 목록. '돌아갈 자리가 있다'를 화면에서 보이게 하는 것이 목적이다."""
    return {"backups": list_backups()}
