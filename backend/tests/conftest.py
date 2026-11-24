# -*- coding: utf-8 -*-
"""테스트 공용 준비물.

지켜야 할 것(CLAUDE.md 6장 '코드 습관·테스트'):
- 실DB 로 돌리지 않는다. 테스트마다 임시 DB 로 `db.DB_PATH`·`db.BACKUP_DIR` 를 갈아끼운다.
- 환경변수(AI 키)는 `app.main` import **뒤에** 치운다 — import 때 .env 가 로드되어 되살아난다.
- TestClient 를 컨텍스트매니저로 쓰지 않으므로 lifespan 이 안 돈다 → `init_db()` 를 직접 부른다.
- AI 는 진짜로 부르지 않는다. `fake_ai` 로 가짜 공급자를 끼운다.
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
MOCK = ROOT / "모의데이터"          # 시연용 가상 자료 — 문서 읽기 시험 자료로도 쓴다
sys.path.insert(0, str(BACKEND))

from app import db                  # noqa: E402
from app import main                # noqa: E402  (.env 가 여기서 로드된다)

# import 뒤에 치운다. 남겨 두면 시험 중에 실제 API 를 부를 수 있다.
for _k in list(os.environ):
    if _k.startswith(("LLM_", "AI_", "OPENAI_", "ANTHROPIC_", "GEMINI_", "COMPAT_")):
        del os.environ[_k]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """임시 DB 위에 올린 앱. 테스트마다 새 DB."""
    from fastapi.testclient import TestClient
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "workbench.db")
    monkeypatch.setattr(db, "BACKUP_DIR", tmp_path / "backups")
    db.init_db()
    # 실제 쓰임과 같은 주소로 — 앱은 이 PC 주소(127.0.0.1·localhost)가 아닌 Host 를 거절한다(security.py)
    return TestClient(main.app, base_url="http://127.0.0.1:8000")


@pytest.fixture
def project(client):
    """업무 하나를 만들어 id 를 돌려준다."""
    r = client.post("/api/projects", json={"name": "시험 업무", "doc_type": "공모사업 계획서"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


class FakeProvider:
    """정해 둔 답을 돌려주는 가짜 AI. 받은 메시지는 `calls` 에 남는다."""
    name = "fake"
    model = "fake-model"

    def __init__(self, answer: str):
        self.answer = answer
        self.calls = []

    def complete(self, messages, **kw):
        self.calls.append(messages)
        return self.answer


@pytest.fixture
def fake_ai(monkeypatch):
    """`fake_ai(answer, module)` — 그 모듈이 import 해 둔 get_provider 를 가짜로 바꾼다."""
    def install(answer: str, module):
        fp = FakeProvider(answer)
        monkeypatch.setattr(module, "get_provider", lambda *a, **k: fp)
        return fp
    return install


def mock_file(prefix: str, sub: str = "") -> Path:
    """모의데이터(또는 그 아래 sub 폴더)에서 이름이 prefix 로 시작하는 파일 하나."""
    found = sorted((MOCK / sub).glob(prefix + "*"))
    assert found, f"모의데이터에 {prefix}* 파일이 없습니다"
    return found[0]
