# -*- coding: utf-8 -*-
"""DB 초기화·마이그레이션의 데이터 보존, 그리고 AI 를 부르지 않는 설문 규칙."""
from app import db
from app.services import survey


def test_init_db를_다시_돌려도_데이터가_남는다(client, project):
    client.post(f"/api/projects/{project}/resources", json={"name": "자료", "text": "본문"})
    db.init_db()                   # 앱을 다시 켠 것과 같다(마이그레이션 재실행)
    db.init_db()
    assert client.get(f"/api/projects/{project}/resources").json()[0]["text"] == "본문"


def test_백업은_DB가_있을_때만_만든다(client, project):
    path = db.backup_db()
    assert path is not None and path.exists()


def test_목표_응답_수는_유한_모집단_보정을_한다():
    # docstring 의 예: 6,100명 · ±5%p → 보정 없이 385명, 보정하면 362명
    assert survey.target_n(0, 5) == 385
    assert survey.target_n(6100, 5) == 362
    assert survey.target_n(6100, 0) == 0


def test_오차범위와_목표_응답_수는_서로_맞는다():
    m = survey.margin_of(362, 6100)
    assert 4.9 <= m <= 5.1
