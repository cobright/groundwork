# -*- coding: utf-8 -*-
"""AI 설정 — 화면에서 넣은 값이 `.env` 보다 앞선다. 일의 무게에 따라 등급을 나눈다.

왜 DB 에 두는가:
  `.env` 는 **시작할 때 한 번** 읽는다. 그래서 키를 바꾸려면 파일을 찾아 열고 고치고
  프로그램을 껐다 켜야 했다. 담당자에게는 이 세 단계가 각각 벽이다(원칙 4:
  기능은 화면 안에서 버튼 하나로 끝나야 한다). `settings` 표에 두면 저장 즉시 반영된다.

`.env` 를 없애지 않는 이유:
  포터블 꾸러미를 만들어 주는 쪽(관리자)이 키를 미리 넣어 반입할 수 있어야 한다.
  그래서 **화면 값이 있으면 그것, 없으면 .env** 순서로 읽고, 어느 쪽에서 왔는지도 알려 준다.

보관 위치에 대한 정직한 말:
  키는 이 PC 의 `workbench.db` 에 그대로(암호화 없이) 들어간다. `.env` 와 같은 수준이며,
  DB 파일은 포터블 꾸러미에 딸려 가지 않는다. 화면에도 이 사실을 적는다.

등급(빠름·기본·정밀)을 두는 이유(v0.26):
  AI 를 부르는 일은 아홉 가지인데 모델이 하나면, 가벼운 일엔 느리고 판단이 필요한 일엔 약하다.
  그렇다고 일마다 모델을 고르게 하면 담당자가 채울 칸이 아홉 개가 된다. 그래서 설정은
  **등급 세 칸(회사 + 모델)** 만 두고, 어떤 일이 어느 등급인지는 `TASKS` 한 곳에서 정한다.
  한 사람이 쓰는 도구라 비용 차이는 크지 않다 — 나누는 값은 기다리는 시간과 어려운 일의 품질이다.

기본 등급이 예전 키를 그대로 쓰는 이유:
  기본 등급은 `LLM_PROVIDER` + `OPENAI_MODEL`(등) 에 둔다. 이미 설정해 둔 PC 와 관리자가
  채워 반입한 `.env` 가 아무것도 고치지 않고 예전처럼 동작해야 한다.
  빠름·정밀은 회사를 비워 두면 기본 등급을 **통째로**(회사까지) 따른다.
"""
from __future__ import annotations

import os

from ..db import connect

PREFIX = "ai."          # settings 표에서 AI 설정만 모아 두는 앞머리

PROVIDERS = [
    {"name": "openai", "label": "OpenAI", "key_env": "OPENAI_API_KEY",
     "model_env": "OPENAI_MODEL", "where": "platform.openai.com 의 API keys"},
    {"name": "claude", "label": "Claude", "key_env": "ANTHROPIC_API_KEY",
     "model_env": "ANTHROPIC_MODEL", "where": "console.anthropic.com 의 API keys"},
    {"name": "gemini", "label": "Gemini", "key_env": "GEMINI_API_KEY",
     "model_env": "GEMINI_MODEL", "where": "aistudio.google.com 의 API key"},
]
_BY_NAME = {p["name"]: p for p in PROVIDERS}

TIERS = [
    {"name": "fast", "label": "빠름", "hint": "사람이 앞에서 기다리는 가벼운 일"},
    {"name": "base", "label": "기본", "hint": "읽고 뽑아내는 일 — 결과는 사람이 확정합니다"},
    {"name": "deep", "label": "정밀", "hint": "판단이 필요하고, 놓치면 최종본까지 가는 일"},
]
TIER_NAMES = [t["name"] for t in TIERS]
_TIER_LABEL = {t["name"]: t["label"] for t in TIERS}

# 일 → 등급. **배정은 여기 한 곳에서만 한다.** 호출부는 무슨 일인지(task)만 말한다.
TASKS = {
    "statement":          ("fast", "담당자 진술 쪼개기"),
    "resource_analysis":  ("base", "자료 분석(요청 대조 포함)"),
    "guideline_analysis": ("base", "공모 가이드라인 판정·문구 다듬기"),
    "draft_brief":        ("base", "보고전 초고"),
    "review_structure":   ("base", "구조 검토"),
    "draft_plan":         ("deep", "계획서 초고"),
    "review_fact":        ("deep", "사실확인 검토"),
    "review_technical":   ("deep", "기술 검토"),
    "review_critique":    ("deep", "비평"),
}

# 등급별 추천 모델(2026-09 각 사 공식 문서 기준). 모델 이름은 몇 달이면 바뀐다 —
# 그래서 화면에서 그 회사의 지금 목록을 불러와 고를 수 있게 했다(routers/setup.py).
RECOMMENDED = {
    "openai": {"fast": "gpt-5.6-luna", "base": "gpt-5.6-terra", "deep": "gpt-5.6-sol"},
    "claude": {"fast": "claude-haiku-4-5", "base": "claude-sonnet-5", "deep": "claude-opus-5"},
    "gemini": {"fast": "gemini-3.5-flash-lite", "base": "gemini-3.8-flash", "deep": "gemini-3.1-pro-preview"},
}

# 정밀 모델은 생각이 길다. 60초로 끊으면 문서 전체 검토가 중간에 잘린다.
TIMEOUT = {"fast": 60, "base": 120, "deep": 180}


def _db_get(key: str) -> str | None:
    with connect() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (PREFIX + key,)).fetchone()
    return r["value"] if r else None


def _db_set(key: str, value: str) -> None:
    with connect() as c:
        if value == "":
            c.execute("DELETE FROM settings WHERE key=?", (PREFIX + key,))
        else:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (PREFIX + key, value))


def value(env_name: str, default: str = "") -> str:
    """화면 값 → .env → 기본값 순서."""
    v = _db_get(env_name)
    if v:
        return v
    return os.getenv(env_name, "") or default


def source(env_name: str) -> str:
    """이 값이 어디서 왔는지. 화면에 적어 주지 않으면 '분명히 넣었는데 왜 안 되지'가 된다."""
    if _db_get(env_name):
        return "화면"
    if os.getenv(env_name, ""):
        return ".env"
    return "없음"


def _tier_keys(tier: str) -> tuple[str, str]:
    """빠름·정밀 등급의 저장 키. 기본 등급은 예전 키(LLM_PROVIDER, *_MODEL)를 쓴다."""
    return f"AI_{tier.upper()}_PROVIDER", f"AI_{tier.upper()}_MODEL"


def current_provider() -> str:
    """기본 등급의 회사."""
    v = value("LLM_PROVIDER", "openai").lower()
    return v if v in _BY_NAME else "openai"


def task_tier(task: str | None) -> str:
    if task is None:
        return "base"
    if task not in TASKS:
        raise ValueError(f"알 수 없는 AI 작업: {task}")
    return TASKS[task][0]


def resolve(tier: str = "base", override: str | None = None) -> dict:
    """등급 → 실제로 쓸 (회사, 모델). 화면 표시와 실제 호출이 **같은 함수**를 쓴다(어긋나지 않게).

    override 는 작업 화면에서 고른 회사다. 같은 회사면 설정 그대로, 다른 회사면
    그 회사의 모델 설정(기본 등급일 때) 또는 추천값을 쓴다.
    """
    if tier not in TIER_NAMES:
        raise ValueError(f"알 수 없는 등급: {tier}")
    inherits = False
    if tier == "base":
        p, p_src = current_provider(), source("LLM_PROVIDER")
        m_env = _BY_NAME[p]["model_env"]
        m, m_src = value(m_env), source(m_env)
    else:
        pk, mk = _tier_keys(tier)
        tp = value(pk).lower()
        if tp in _BY_NAME:
            p, p_src = tp, source(pk)
            m, m_src = value(mk), source(mk)
        else:                                   # 비어 있으면 기본 등급을 통째로 따른다
            inherits = True
            b = resolve("base")
            p, p_src, m, m_src = b["provider"], b["provider_source"], b["model"], b["model_source"]

    ov = (override or "").lower()
    if ov and ov != p:
        if ov not in _BY_NAME:
            raise ValueError(f"알 수 없는 공급자: {ov} (openai/claude/gemini 중 하나)")
        p, p_src = ov, "작업 화면"
        if tier == "base" or inherits:
            m_env = _BY_NAME[p]["model_env"]
            m, m_src = value(m_env), source(m_env)
        else:
            m, m_src = "", "없음"
    if not m:
        m, m_src = RECOMMENDED[p]["base" if inherits else tier], "추천값"
    return {"tier": tier, "provider": p, "provider_source": p_src, "model": m,
            "model_source": m_src, "inherits": inherits, "timeout": TIMEOUT[tier]}


def model_if_blank(provider: str, tier: str) -> str:
    """모델 칸을 비우고 저장하면 실제로 쓰일 모델(.env 값이 있으면 그것, 없으면 추천값).
    설정 화면의 '저장 전 시험'이 저장 뒤와 **같은 모델**로 시험하게 하려고 둔다."""
    env = _BY_NAME[provider]["model_env"] if tier == "base" else _tier_keys(tier)[1]
    return os.getenv(env, "") or RECOMMENDED[provider][tier]


def mask(secret: str) -> str:
    """키는 절대 그대로 돌려주지 않는다. 맞게 넣었는지 확인할 만큼만 보여준다."""
    if not secret:
        return ""
    return ("·" * 8) + secret[-4:] if len(secret) > 4 else "·" * len(secret)


def snapshot() -> dict:
    """화면에 보여줄 현재 설정(키 원문 없음).

    set_provider / set_model 은 **입력칸에 채울 값**이다(빠름·정밀의 "" = 기본과 같게, 모델 "" = 추천값).
    provider / model 은 **실제로 쓰일 값**이다. 둘을 나눠야 '비워 두면 무엇을 쓰는지'를 보여줄 수 있다.
    """
    tiers = []
    for t in TIERS:
        r = resolve(t["name"])
        typed = r["model"] if r["model_source"] in ("화면", ".env") and not r["inherits"] else ""
        tiers.append({**r, "label": t["label"], "hint": t["hint"],
                      "set_provider": "" if r["inherits"] else r["provider"],
                      "set_model": typed,
                      "tasks": [label for (tier, label) in TASKS.values() if tier == t["name"]],
                      "key_set": bool(value(_BY_NAME[r["provider"]]["key_env"]))})
    keys = []
    for p in PROVIDERS:
        key = value(p["key_env"])
        keys.append({"name": p["name"], "label": p["label"], "where": p["where"],
                     "key_set": bool(key), "key_masked": mask(key), "key_source": source(p["key_env"]),
                     "used_by": [t["label"] for t in tiers if t["provider"] == p["name"]]})
    return {"tiers": tiers, "keys": keys,
            "tasks": [{"task": k, "label": label, "tier": tier, "tier_label": _TIER_LABEL[tier]}
                      for k, (tier, label) in TASKS.items()],
            "providers": [{"name": p["name"], "label": p["label"]} for p in PROVIDERS],
            "recommended": RECOMMENDED}


def apply(tiers: dict | None = None, keys: dict | None = None) -> None:
    """화면에서 온 값을 저장한다. **보낸 것만** 바꾼다(None = 그대로, "" = 화면 값 지움).

    빈 문자열을 '지우기'로 삼는 이유: 화면에는 키를 다시 보여주지 않으므로,
    빈 칸으로 저장을 누르는 것이 '그대로 두기'여야 실수로 키가 날아가지 않는다.
    지우기는 별도의 버튼에서 명시적으로 "" 를 보낸다.

    빠름·정밀의 회사를 바꾸면서 모델을 함께 보내지 않았다면 그 등급의 모델 값을 지운다 —
    다른 회사의 모델 이름이 남아 있으면 부를 때마다 '모델을 찾지 못했습니다'가 된다.
    """
    tiers = tiers or {}
    for tier in ("base", "fast", "deep"):
        ent = tiers.get(tier)
        if not ent:
            continue
        prov, model = ent.get("provider"), ent.get("model")
        if prov is not None:
            prov = prov.strip().lower()
            if prov and prov not in _BY_NAME:
                raise ValueError(f"알 수 없는 공급자: {prov} (openai/claude/gemini 중 하나)")
        if tier == "base":
            if prov is not None:
                _db_set("LLM_PROVIDER", prov)
            if model is not None:                # 기본의 모델 키는 (방금 정한) 기본 회사의 것
                _db_set(_BY_NAME[current_provider()]["model_env"], model.strip())
        else:
            pk, mk = _tier_keys(tier)
            if prov is not None:
                changed = prov != value(pk).lower()
                _db_set(pk, prov)
                if changed and model is None:
                    _db_set(mk, "")
            if model is not None:
                _db_set(mk, model.strip())
    for name, key in (keys or {}).items():
        p = _BY_NAME.get(name)
        if p and key is not None:
            _db_set(p["key_env"], key.strip())
