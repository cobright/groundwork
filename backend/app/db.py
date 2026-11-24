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


BACKUP_DIR = DB_PATH.parent / "backups"
KEEP_BACKUPS = 7          # 하루 한 개 × 일주일. 더 두면 폴더만 무거워진다.


def backup_db() -> Path | None:
    """시작할 때 하루 한 번 DB 를 통째로 복사해 둔다.

    왜: 이 앱에는 되돌리기가 거의 없고, 실제로 v0.19에 진행 중이던 계획서의
    목차 19개·집필카드 19개를 잃은 적이 있다. 확인 문구를 고쳐 재발은 막았지만
    **돌아갈 자리**가 없었다. 백업은 그 자리다.

    마이그레이션보다 **먼저** 부른다 — 새 버전이 DB 를 잘못 건드렸을 때
    손대기 전 파일이 남아 있어야 한다.
    하루 한 개인 이유: 아침에 켠 뒤 오후에 사고가 나면, 그날 첫 상태가 필요한 것이다.
    실패해도 앱은 그대로 뜬다(백업 때문에 프로그램이 안 켜지면 더 나쁘다).
    """
    try:
        if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
            return None
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = BACKUP_DIR / f"workbench_{datetime.now().strftime('%Y%m%d')}.db"
        if target.exists():
            return target
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(target)
        try:
            with dst:
                src.backup(dst)      # 파일 복사가 아니라 sqlite 가 보장하는 백업
        finally:
            src.close()
            dst.close()
        old = sorted(BACKUP_DIR.glob("workbench_*.db"))[:-KEEP_BACKUPS]
        for f in old:
            try:
                f.unlink()
            except OSError:
                pass
        return target
    except Exception as e:                     # noqa: BLE001 — 백업 실패가 기동을 막으면 안 된다
        print(f"[백업] 건너뜀: {e}")
        return None


def list_backups() -> list[dict]:
    """보관 중인 백업 목록(최신 순). 화면에 '돌아갈 자리가 있다'를 보여주기 위한 것."""
    if not BACKUP_DIR.exists():
        return []
    out = []
    for f in sorted(BACKUP_DIR.glob("workbench_*.db"), reverse=True):
        st = f.stat()
        out.append({"name": f.name, "date": f.stem.replace("workbench_", ""),
                    "size": st.st_size, "path": str(f)})
    return out


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
                archived_at TEXT NOT NULL DEFAULT '',   -- 보관함(캐비넷)에 넣은 시각. 비어 있으면 활성.
                archive_note TEXT NOT NULL DEFAULT '',  -- 왜 보관했는지 한 줄
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
                note TEXT NOT NULL DEFAULT '',           -- 담당자 메모(자료 내용이 아니라 사람의 말)
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
            -- 한글(HWPX) 양식 보관함. 사용자가 올린 양식 원본을 그대로 담아두고,
            -- 최종본을 내보낼 때 이 중 하나를 골라 그 구조에 채워 넣는다.
            -- 공모 가이드라인 보관함. 공모 한 건에 파일이 여러 개 온다
            -- (공고 / 수립 가이드라인 / 서식). 종류를 나눠 담고 원본을 그대로 둔다.
            -- 가이드라인은 '근거'가 아니라 '요구사항'이므로 resources 에 넣지 않는다.
            CREATE TABLE IF NOT EXISTS guidelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT '',        -- 사용자가 붙인 이름
                filename TEXT NOT NULL DEFAULT '',    -- 올린 파일 이름
                doc_kind TEXT NOT NULL DEFAULT '공고', -- 공고/수립 가이드라인/서식
                data BLOB NOT NULL,                   -- 원본 그대로(정정 공고 대비)
                size INTEGER NOT NULL DEFAULT 0,
                file_kind TEXT NOT NULL DEFAULT '',   -- pdf/hwpx/hwp (읽은 결과)
                pages INTEGER NOT NULL DEFAULT 0,
                blocks INTEGER NOT NULL DEFAULT 0,
                read_note TEXT NOT NULL DEFAULT '',   -- 못 읽은 것이 있으면 사람이 읽는 말
                range_start INTEGER NOT NULL DEFAULT -1,  -- 사람이 고른 분석 구간
                range_end INTEGER NOT NULL DEFAULT -1,
                analysis TEXT NOT NULL DEFAULT '',    -- 마지막 분석 결과(JSON). 제안일 뿐이다.
                analyzed_at TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            -- 목차를 통째로 갈아끼우기 '직전'의 상태. 되돌리기의 근거가 된다.
            -- 목차 항목은 바뀌지 않는 uid 로 식별되므로 그대로 적어 두었다가 되살릴 수 있다.
            CREATE TABLE IF NOT EXISTS outline_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                taken_at TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',      -- 왜 찍혔는지(목차 교체/직접 저장)
                summary TEXT NOT NULL DEFAULT '',     -- 사람이 읽는 한 줄(항목 12 · 카드 12 · 본문 3)
                data TEXT NOT NULL,                   -- 목차·카드·본문·검토의견·연결 (JSON)
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            -- 자료의 원본 파일. resources 에 BLOB 을 넣지 않고 딴 표에 두는 이유:
            -- 자료 목록은 SELECT * 로 읽는 곳이 여럿이라, 같은 표에 두면 목록을 부를 때마다
            -- 수십 MB 가 딸려 나온다. 자료 1건에 파일 1개(붙여넣기로 만든 자료는 없음).
            CREATE TABLE IF NOT EXISTS resource_files (
                resource_id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL DEFAULT '',    -- 올린 파일 이름(그대로 내려받게 한다)
                file_kind TEXT NOT NULL DEFAULT '',   -- pdf/hwpx/hwp/xlsx/docx (읽은 결과)
                size INTEGER NOT NULL DEFAULT 0,
                pages INTEGER NOT NULL DEFAULT 0,
                blocks INTEGER NOT NULL DEFAULT 0,
                read_note TEXT NOT NULL DEFAULT '',   -- 못 읽은 것이 있으면 사람이 읽는 말
                data BLOB NOT NULL,                   -- 원본 그대로(원문 대조는 사람의 몫)
                created_at TEXT NOT NULL,
                FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE CASCADE
            );
            -- 주민 설문(docs/design/survey.md). "설계한 설문지가 곧 분석 틀이다" —
            -- 계획서의 주장(근거 지도) → 문항 → 분석 계획을 **수집 전에** 정해 둔다.
            -- 지금은 ①근거 지도 ②문항 설계 ③점검 ④폼으로 옮기기까지(응답 파일은 실물을 받은 뒤).
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                target TEXT NOT NULL DEFAULT '',      -- 조사 대상(예: 관내 경로당 회원)
                method TEXT NOT NULL DEFAULT '온라인 폼',
                period_from TEXT NOT NULL DEFAULT '',
                period_to TEXT NOT NULL DEFAULT '',
                population INTEGER NOT NULL DEFAULT 0, -- 대상 인구(목표 응답 수 계산에 쓴다)
                margin REAL NOT NULL DEFAULT 5,        -- 원하는 오차범위(±%p, 95% 신뢰수준)
                exported_at TEXT NOT NULL DEFAULT '',  -- 마지막으로 폼 옮기기 표를 내려받은 때
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            -- 근거 지도: 목차 항목의 주장 하나 ↔ 무엇으로 받치나(설문/통계/진술/미정).
            -- 목차 uid 에 묶인다 → put_outline 이 연결만 끊고, 되돌리기가 다시 잇는다(근거와 같은 규칙).
            CREATE TABLE IF NOT EXISTS survey_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                node_uid TEXT,
                claim TEXT NOT NULL DEFAULT '',
                basis TEXT NOT NULL DEFAULT '미정',
                note TEXT NOT NULL DEFAULT '',
                sort INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            -- 문항. 다른 문항을 가리킬 때(분석 계획의 교차, 분기)는 id 로 가리킨다(순서를 바꿔도 따라온다).
            CREATE TABLE IF NOT EXISTS survey_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                sort INTEGER NOT NULL DEFAULT 0,
                text TEXT NOT NULL DEFAULT '',
                qtype TEXT NOT NULL DEFAULT '단일',     -- 단일/복수/척도/순위/숫자/주관식
                options TEXT NOT NULL DEFAULT '[]',    -- 보기(JSON 배열)
                required INTEGER NOT NULL DEFAULT 1,
                other_allowed INTEGER NOT NULL DEFAULT 0,
                rank_k INTEGER NOT NULL DEFAULT 3,     -- 순위 문항: 몇 순위까지 받나
                profile INTEGER NOT NULL DEFAULT 0,    -- 응답자 특성 문항(연령·읍면 등)
                claim_id INTEGER,                      -- 받치는 주장(근거 지도)
                cross_with TEXT NOT NULL DEFAULT '[]', -- 분석 계획: 견줄 문항 id(JSON 배열)
                branch TEXT NOT NULL DEFAULT '{}',     -- 분기: {보기: 문항 id | "end"}
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
                FOREIGN KEY (claim_id) REFERENCES survey_claims(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS hwpx_forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',        -- 사용자가 붙인 이름
                filename TEXT NOT NULL DEFAULT '',    -- 올린 파일 이름
                data BLOB NOT NULL,                   -- 양식 원본(.hwpx) 그대로
                size INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',        -- 어떤 용도의 양식인지 메모
                supported INTEGER NOT NULL DEFAULT 1, -- 우리가 채울 수 있는 구조인가
                reason TEXT NOT NULL DEFAULT '',      -- 못 채운다면 왜인지(사람이 읽는 말)
                created_at TEXT NOT NULL
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
    # 보관함: 기존 업무는 archived_at='' 이 되어 모두 활성으로 남는다.
    if "archived_at" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN archived_at TEXT NOT NULL DEFAULT ''")
    if "archive_note" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN archive_note TEXT NOT NULL DEFAULT ''")
    # 문서 유형 이름을 중립어로 바꿨다(2026-11-24). 이미 만든 업무도 새 이름으로 옮긴다 —
    # 옛 이름으로 남으면 틀 목록에서 못 찾아 보고전 뽑기 등이 '모르는 유형'이 된다. 여러 번 돌아도 같다.
    from .services.templates import RENAMED_TYPES
    for old, new in RENAMED_TYPES.items():
        conn.execute("UPDATE projects SET doc_type=? WHERE doc_type=?", (new, old))

    # evidence.source_changed
    ecols =[r["name"] for r in conn.execute("PRAGMA table_info(evidence)").fetchall()]
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

    # 자료에 담당자 메모(v0.21). 자료 '내용'이 아니라 그 자료를 어떻게 볼 것인지에 대한
    # 사람의 말이므로, 이 칸을 고쳐도 재분석·근거 변경신호를 켜지 않는다(routers/resources.py).
    rcols2 = [r["name"] for r in conn.execute("PRAGMA table_info(resources)").fetchall()]
    if "note" not in rcols2:
        conn.execute("ALTER TABLE resources ADD COLUMN note TEXT NOT NULL DEFAULT ''")

    # 기본 부서 폴더 시드(부서가 하나도 없을 때만)
    n = conn.execute("SELECT COUNT(*) c FROM departments").fetchone()["c"]
    if n == 0:
        for i, name in enumerate(["기획예산실", "총무과", "인구정책과", "문화관광과"]):
            conn.execute("INSERT INTO departments(name, sort, created_at) VALUES(?,?,?)", (name, i, now()))

    # 양식 보관함: 지원 여부 진단 컬럼
    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hwpx_forms'").fetchone():
        fcols = [r["name"] for r in conn.execute("PRAGMA table_info(hwpx_forms)").fetchall()]
        if "supported" not in fcols:
            conn.execute("ALTER TABLE hwpx_forms ADD COLUMN supported INTEGER NOT NULL DEFAULT 1")
        if "reason" not in fcols:
            conn.execute("ALTER TABLE hwpx_forms ADD COLUMN reason TEXT NOT NULL DEFAULT ''")

    # 공모 가이드라인 보관함(v0.20). 표는 CREATE IF NOT EXISTS 로 생기고,
    # 여기서는 나중에 컬럼이 늘었을 때를 대비해 확인만 한다.
    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='guidelines'").fetchone():
        gcols = [r["name"] for r in conn.execute("PRAGMA table_info(guidelines)").fetchall()]
        for col, ddl in (("range_start", "INTEGER NOT NULL DEFAULT -1"),
                         ("range_end", "INTEGER NOT NULL DEFAULT -1"),
                         ("read_note", "TEXT NOT NULL DEFAULT ''"),
                         ("doc_kind", "TEXT NOT NULL DEFAULT '공고'")):
            if col not in gcols:
                conn.execute(f"ALTER TABLE guidelines ADD COLUMN {col} {ddl}")

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
