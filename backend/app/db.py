# -*- coding: utf-8 -*-
"""SQLite 접근 계층.
핵심 설계: 목차 항목은 바뀌지 않는 uid 로 식별한다.
집필카드는 목차 번호가 아니라 uid 에 묶이므로, 목차를 재정렬해도 카드가 보존된다.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "workbench.db"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                doc_type TEXT NOT NULL DEFAULT '',
                purpose TEXT NOT NULL DEFAULT '',
                audience TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '정상 진행',
                stage TEXT NOT NULL DEFAULT '업무준비',
                due_date TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outline_nodes (
                project_id INTEGER NOT NULL,
                uid TEXT NOT NULL,
                parent_uid TEXT,
                sort INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (project_id, uid),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS writing_cards (
                project_id INTEGER NOT NULL,
                node_uid TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT '',
                question TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                length TEXT NOT NULL DEFAULT '1쪽',
                status TEXT NOT NULL DEFAULT '작성 전',
                PRIMARY KEY (project_id, node_uid),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            -- 자료실: 등록된 원자료
            -- 부서 폴더(공통자료실). 자유 생성/이름변경/삭제.
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                sort INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT ''
            );
            -- 자료. 업무 소속(project_id) 또는 공통자료실 소속(dept_id) 중 하나.
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,                      -- 업무 고유 자료면 설정
                dept_id INTEGER,                         -- 공통자료실 자료면 설정
                name TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT '내부자료',
                source_org TEXT NOT NULL DEFAULT '',
                base_date TEXT NOT NULL DEFAULT '',
                trust TEXT NOT NULL DEFAULT '보통',
                text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (dept_id) REFERENCES departments(id)
            );
            -- 업무가 공통자료를 참조(복사 아님).
            CREATE TABLE IF NOT EXISTS resource_refs (
                project_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (project_id, resource_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
            );
            -- AI 자료분석 결과: 사용자가 확정해야 근거로 승격
            CREATE TABLE IF NOT EXISTS resource_analysis (
                resource_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',         -- 핵심 요약
                key_points TEXT NOT NULL DEFAULT '[]',    -- 주요 내용/수치 (JSON 배열)
                usable_for TEXT NOT NULL DEFAULT '[]',    -- 활용 가능 목차/주장 (JSON 배열)
                cautions TEXT NOT NULL DEFAULT '[]',      -- 주의사항 (JSON 배열)
                state TEXT NOT NULL DEFAULT '분석 전',      -- 분석 전/분석 완료/사용자 확정
                model TEXT NOT NULL DEFAULT '',           -- 어떤 모델이 분석했는지
                analyzed_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
            );
            -- 근거표: 주장 ↔ 근거자료 연결
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                claim TEXT NOT NULL DEFAULT '',           -- 주장/판단
                resource_id INTEGER,                      -- 근거자료 (없으면 '근거 없음')
                locator TEXT NOT NULL DEFAULT '',         -- 원문 위치(쪽/표)
                trust TEXT NOT NULL DEFAULT '',           -- A/B/C/D 또는 확인 상태
                status TEXT NOT NULL DEFAULT '확인 필요',   -- 확인/확인 필요/충돌/추정/사용 보류
                node_uid TEXT,                            -- 관련 목차 항목(있으면 연결)
                source_changed INTEGER NOT NULL DEFAULT 0, -- 근거 자료가 수정되면 1
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE SET NULL
            );
            -- 초고 본문: 목차 항목(uid)에 묶여 저장된다(카드처럼 보존).
            CREATE TABLE IF NOT EXISTS drafts (
                project_id INTEGER NOT NULL,
                node_uid TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',            -- 확정된 본문(사용자가 반영한 것)
                ai_suggestion TEXT NOT NULL DEFAULT '',   -- AI가 마지막에 제안한 초안(미반영 가능)
                strictness TEXT NOT NULL DEFAULT '엄격',    -- 마지막 생성 강도
                model TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (project_id, node_uid),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            -- 검토의견: 네 검토자(사실확인/기술/구조/비평)가 공용으로 쓰는 표.
            -- 검토자는 본문을 고치지 않고 여기에 의견만 남긴다. 처리는 사용자가 한다.
            CREATE TABLE IF NOT EXISTS review_opinions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                node_uid TEXT,                           -- 대상 목차(있으면)
                kind TEXT NOT NULL DEFAULT '사실확인',      -- 사실확인/기술검토/구조검토/비평
                severity TEXT NOT NULL DEFAULT '일반',      -- 중대/중요/일반/참고
                target_text TEXT NOT NULL DEFAULT '',      -- 문제가 된 본문 조각(있으면)
                problem TEXT NOT NULL DEFAULT '',          -- 무엇이 문제인가
                suggestion TEXT NOT NULL DEFAULT '',       -- 수정 제안(반영은 사용자 몫)
                basis TEXT NOT NULL DEFAULT '',            -- 판단 근거(어떤 근거/자료에 비추어)
                needs TEXT NOT NULL DEFAULT '',            -- 필요한 조치(담당부서 확인 등)
                status TEXT NOT NULL DEFAULT '미처리',       -- 미처리/확인중/반영/일부반영/반영안함/보류
                user_note TEXT NOT NULL DEFAULT '',        -- 미반영 사유 등 사용자 메모
                source TEXT NOT NULL DEFAULT 'AI',         -- AI/담당부서/사용자 등 출처 구분
                model TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            -- 부서 자료요청 대장: '필요한 자료' 항목을 모아 부서별로 요청·추적.
            CREATE TABLE IF NOT EXISTS data_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                node_uid TEXT,                           -- 어느 목차에서 필요한가
                need TEXT NOT NULL DEFAULT '',            -- 필요한 자료 내용
                dept_id INTEGER,                         -- 요청 대상 부서
                status TEXT NOT NULL DEFAULT '필요',       -- 필요/요청함/회신옴/반영/보류
                origin TEXT NOT NULL DEFAULT 'user',      -- draft/review/user
                origin_ref TEXT NOT NULL DEFAULT '',      -- 자동수집 중복 방지 키
                note TEXT NOT NULL DEFAULT '',
                requested_at TEXT NOT NULL DEFAULT '',    -- 요청(발송)일
                due_date TEXT NOT NULL DEFAULT '',        -- 회신 마감일
                received_note TEXT NOT NULL DEFAULT '',   -- 회신 내용 메모
                received_resource_id INTEGER,            -- 회신자료를 등록한 자료 id
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (dept_id) REFERENCES departments(id)
            );
            -- 앱 전역 설정(키-값): 예) author_name = '내 이름'
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        _migrate(conn)


def _migrate(conn) -> None:
    """기존 DB에도 새 구조를 안전하게 반영한다(있으면 건너뜀)."""
    # projects.due_date
    pcols = [r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
    if "due_date" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN due_date TEXT NOT NULL DEFAULT ''")
    # evidence.source_changed
    ecols = [r["name"] for r in conn.execute("PRAGMA table_info(evidence)").fetchall()]
    if "source_changed" not in ecols:
        conn.execute("ALTER TABLE evidence ADD COLUMN source_changed INTEGER NOT NULL DEFAULT 0")

    # resources: dept_id 없으면 테이블 재구성(project_id 널 허용 + dept_id 추가)
    rcols = [r["name"] for r in conn.execute("PRAGMA table_info(resources)").fetchall()]
    if "dept_id" not in rcols:
        conn.commit()  # 트랜잭션이 없어야 PRAGMA foreign_keys 가 적용됨
        conn.execute("PRAGMA foreign_keys=OFF")  # DROP 시 자식(analysis/evidence) 연쇄삭제 방지
        conn.executescript(
            """
            CREATE TABLE resources_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                dept_id INTEGER,
                name TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT '내부자료',
                source_org TEXT NOT NULL DEFAULT '',
                base_date TEXT NOT NULL DEFAULT '',
                trust TEXT NOT NULL DEFAULT '보통',
                text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (dept_id) REFERENCES departments(id)
            );
            INSERT INTO resources_new (id, project_id, dept_id, name, kind, source_org, base_date, trust, text, created_at)
                SELECT id, project_id, NULL, name, kind, source_org, base_date, trust, text, created_at FROM resources;
            DROP TABLE resources;
            ALTER TABLE resources_new RENAME TO resources;
            """
        )
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")

    # 기본 부서 폴더 시드(부서가 하나도 없을 때만)
    n = conn.execute("SELECT COUNT(*) c FROM departments").fetchone()["c"]
    if n == 0:
        for i, name in enumerate(["기획예산실", "총무과", "인구정책과", "문화관광과"]):
            conn.execute("INSERT INTO departments(name, sort, created_at) VALUES(?,?,?)", (name, i, now()))

    # 자료요청 ②: 요청일·마감일·회신자료 컬럼
    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data_requests'").fetchone():
        dcols = [r["name"] for r in conn.execute("PRAGMA table_info(data_requests)").fetchall()]
        if "requested_at" not in dcols:
            conn.execute("ALTER TABLE data_requests ADD COLUMN requested_at TEXT NOT NULL DEFAULT ''")
        if "due_date" not in dcols:
            conn.execute("ALTER TABLE data_requests ADD COLUMN due_date TEXT NOT NULL DEFAULT ''")
        if "received_note" not in dcols:
            conn.execute("ALTER TABLE data_requests ADD COLUMN received_note TEXT NOT NULL DEFAULT ''")
        if "received_resource_id" not in dcols:
            conn.execute("ALTER TABLE data_requests ADD COLUMN received_resource_id INTEGER")
