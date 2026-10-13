# CLAUDE.md — AI 행정기획 워크벤치 인수인계

이 문서는 이 저장소에서 **Claude Code(또는 다른 클로드)** 가 작업을 이어갈 때
가장 먼저 읽어야 하는 문서입니다. 이 도구가 무엇이고, 왜 이렇게 설계됐으며,
무엇을 건드리면 안 되는지를 담았습니다. **코드를 바꾸기 전에 이 문서의 원칙을
먼저 지키세요.** 원칙과 충돌하는 "개선"은 개선이 아닙니다.
결정의 경위와 기능별 논점은 `docs/` 에 있습니다 — 무엇을 언제 읽을지는 5장의 표를 보세요.

---

## 0. 한 줄 요약

한국 지방자치단체(군청) 기획 담당자가 **행정문서(공모사업 계획서·군정기획보고서·
군수 관심사업 추진계획서 등)를 작성하는 전 과정**(자료조사 → 초고 → 검토 → 최종본)을
표준화해서 돕는 **로컬 단일 사용자 도구**. FastAPI + React(Vite) + SQLite.

---

## 1. 절대 흔들면 안 되는 설계 원칙 (가장 중요)

이 원칙들은 사용자와 오래 합의하며 세운 것입니다. 리팩터링·기능추가 중에도 반드시 지킵니다.

1. **AI는 제안하고, 사람이 확정한다.** AI가 최종 내용을 스스로 쓰거나 고치지 않는다.
   - 초고 생성은 "제안"이며, 본문 채택은 사람이 한다.
   - 검토자(에이전트)는 **의견만** 낸다. 본문을 직접 수정하지 않는다.
   - 진행상황 보고도 같다: 시스템이 사실을 채우고, 사람은 확인 + 한마디만.

2. **모든 것은 근거(evidence)로 통제된다.** "확정 전엔 근거가 아니다."
   - 자료(resource) → 분석 → **사용자 확정** 을 거쳐야 근거가 된다.
   - 자료가 바뀌면 그 자료를 참조한 모든 곳에 `source_changed=1` 신호가 뜬다.

3. **한 사람이 전부 하지 않는다(분업).** 팀장1+주무관2 같은 실제 조직을 전제.
   - 지금까지 구현한 분업은 **"보이기(visibility)"** 다(협업/동시편집 아님).
   - 주무관이 진행상황을 **파일로 내보내고**, 팀장이 그 파일들을 **폴더로 모아 본다**.
   - **서버를 두지 않는다**(행정·용역업체 모두 서버 운영이 곤란). 메신저 다운로드
     폴더를 통로로 쓴다. 한 방향(주무관→팀장). 실시간 아님.

4. **로컬·설치 최소.** 제약의 정확한 형태는 이렇다(2026-08 사용자 확인):
   - **인터넷은 된다.** 행정망 PC에서 외부 API 호출이 가능하다 → AI 기능이 동작한다.
     (예전 문서에 "행정망엔 인터넷이 없다"고 적혀 있었으나 사실과 다르다.)
   - **파이썬 기본 설치는 가능하지만, 추가 설치는 곤란하다.** 그래서 `pip install`이나
     별도 인스톨러(한컴 애드인, pywin32 COM 등록 등)를 요구하는 설계는 쓰지 않는다.
     필요한 것은 **포터블 꾸러미에 미리 담아** 반입한다(현재 fastapi·python-docx 등이
     그 방식). 새 기능은 **파이썬 표준 라이브러리만으로** 되는 쪽을 우선한다.
   - 외부 서버·클라우드에 우리 데이터를 두지 않는다. 데이터는 로컬 SQLite 한 파일.
   - **Claude Code를 붙이는 것 자체는 가능하지만 사용자가 익숙하지 않다.** 그러므로
     기능은 워크벤치 화면 안에서 버튼 하나로 끝나야 하고, "스킬을 설치해 쓰세요"는
     해법이 아니다. 공개 Claude 스킬은 **참조 구현으로만** 읽는다.

5. **행정 실무의 언어와 감각을 따른다.** 결재란·기안→검토→결재 흐름처럼 이 세계에
   실재하는 것에서 UI 은유를 가져온다. 화려함보다 "통제되고 있다는 느낌".

> 참고(미래): 용역업체(컨설팅사)용 화이트라벨은 용어 사전 + 사용자 유형 설정으로
> 하기로 했으나 **보류**. 메뉴 라벨은 가능하면 한곳에 모아둔다.

---

## 2. 기술 스택 · 실행

- **backend/**: FastAPI + SQLite(순수 sqlite3, ORM 없음). Python 3.11+.
- **frontend/**: React + Vite (빌드 결과 `frontend/dist`를 백엔드가 정적 서빙).
- **DB**: `backend/data/workbench.db` (자동 생성·자동 마이그레이션).
- **LLM**: `.env`의 `LLM_PROVIDER`로 openai|claude|gemini 선택. 키 없으면 해당
  기능만 502로 명확히 실패(앱은 정상 기동). `.env`는 **시작 시 1회** 로드 → 편집 후 재시작.

### 개발 실행 (개발 PC)
- Windows: `1_SETUP.bat`(최초 1회, venv+npm 설치) → `2_START.bat`(백엔드 8000 +
  프런트 5173 두 창, 브라우저 자동 열기). 프런트는 vite proxy로 `/api`→8000.
- 수동: `cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`,
  `python run.py` (플레인 실행: 8000에서 API+빌드된 dist 서빙, 브라우저 자동 열기).
  프런트 개발서버는 `cd frontend && npm install && npm run dev`.

### 포터블 실행 (행정망 배포)
- `portable/포터블_만들기.bat` → 인터넷 되는 윈도우 PC에서 1회 실행.
  파이썬 임베디드(3.11) + 패키지를 담아 `행정기획워크벤치_포터블` 폴더 생성.
- 그 폴더를 행정망 PC로 반입 → 안의 `실행.bat` 더블클릭.
- 자세한 내용은 `portable/사용설명.txt`.

---

## 3. 폴더 구조

```
backend/
  run.py                 포터블/로컬 공용 진입점(경로 안전, 브라우저 자동 열기)
  requirements.txt       fastapi, uvicorn(플레인)+h11, httpx, python-dotenv,
                         pydantic, python-docx, openpyxl
  .env.example           LLM_PROVIDER + 각 provider 키/모델
  app/
    main.py              FastAPI 진입점. .env를 backend 기준으로 로드.
                         라우터 등록. frontend/dist 있으면 "/"로 정적 서빙.
    db.py                SQLite 연결 + 스키마 + _migrate(). 경로는 __file__ 기준.
    routers/
      projects.py        업무 CRUD(부분수정). 마감일 due_date.
      outline.py         목차(트리) + 집필카드(writing_cards)
      resources.py       자료 + AI분석 + 근거표(evidence)
      library.py         공통자료실(부서 폴더/departments) + 승격(promote)
      review.py          검토 실행/의견(review_opinions) 관리
      requests.py        부서 자료요청(data_requests) + xlsx 내보내기
      export.py          최종본(.docx) 점검·생성
      dashboard.py       업무 가로지르는 집계. compute_metrics(c,p)가 핵심 공용 함수.
      report.py          진행상황 보고: 설정(내이름) + 미리보기 + 보고파일(JSON) 생성
      inbox.py           받은 보고: 폴더 지정/읽기 + 폴더 선택창(pick-folder)
      setup.py           설정 화면: AI 연결(등급별 회사·모델 · 모델 목록 불러오기 · 키 · 연결 시험) + 백업 목록
      guidelines.py      공모 가이드라인: 올리기(원본 BLOB) → 범위 고르기 →
                         분석(제안) → 자료 채택. 목차는 프런트가 기존 틀 경로로 심는다.
      statements.py      담당자 진술: 쪼개기(제안) → 채택(확정)
      forms.py           한글(HWPX) 양식 보관함 + 양식에 채워 내보내기
      templates.py       목차 틀 제공(GET /api/templates)
    providers/           LLM 어댑터: base(공통 요청·오류·생각 여유) + openai/claude/gemini
                         + compat(주소를 고르는 OpenAI 호환 서버 — 공통기반 모델)
                         + registry(일 → 등급 → 회사·모델로 어댑터 만들기)
    agents/              검토 서브에이전트: fact_check(사실확인), technical(기술),
                         structure(구조), critique(비평) + common(공용 파싱/조립)
    skills/              반복작업 표준절차: resource_analysis, draft_writing,
                         statement, guideline_analysis(후보 판정·문구 다듬기)
    services/            export_docx.py (.docx 조립: 맑은 고딕 + 근거 부록)
                         templates.py 문서 유형별 목차 틀의 유일한 출처 + family_of(계열 판정)
                         evidence.py  목차에 연결된 근거 모으기(linked_evidence) + 표시(evidence_mark)
                         numbering.py 근거 번호(E-번호)를 만드는 유일한 자리
                         hwpx_fill.py 한글 보고서 양식 채우기 · hwpx_form.py 서식형 양식 분석·자동 배정
                         doc_read.py  pdf/hwpx/hwp/xlsx/docx → 공통 중간형식(문단·표)
                         attachments.py 올린 파일을 자료에 붙이기(읽기+원본 보관 한 곳)
                         snapshot.py  목차 스냅샷(찍기·되돌리기)
                         aiconfig.py  AI 설정: 화면 값(settings) > .env · 등급(빠름/기본/정밀) · 일 배정(TASKS) · 추천 모델
                         formstore.py 양식 보관함에 넣기(검사+저장, 문이 둘이라 한 곳에)
                         progress.py  진행 지표를 사람의 말로(보고 줄 · 근거 주장)
                         gldiff.py    가이드라인 두 분석 견주기(정정 공고)
                         guideline.py 규칙으로 목차·카드·자료후보·배점표 뽑기
frontend/src/
  App.jsx                헤더(지휘 바)+탭 라우팅. 뷰: dashboard/inbox/outline/
                         resources/library/draft/review/requests/final
  api.js                 모든 API 호출 헬퍼(+ reportApi). 오류 detail 안전 포맷.
  outlineModel.js        목차 트리/카드 로직(번호는 렌더 시 계산)
  Dashboard.jsx          초기화면. 업무 카드(결재란 단계 띠 + 미해결 칩 + 마감).
  ResourceRoom / LibraryRoom / DraftRoom / ReviewRoom / RequestRoom /
  FinalRoom / InboxRoom / ReportModal / GuidelineRoom.jsx
  styles.css             상황실 톤 디자인 토큰(:root) + 전 화면 스타일
  Columns.jsx            세 칸 화면의 폭 조절(useColumns): 끌기 · 두 번 눌러 처음 폭 · 옆 칸 접기, 화면별 기억
docs/                    결정의 경위·기능별 논점(5장 표를 보고 필요할 때 연다)
모의데이터/               시연용 가상 공모사업 한 건(공고·정정공고 hwpx, 회신 xlsx/xls, docx, 진술) + 안내.txt
portable/                포터블 조립 스크립트/런처/설명서
```

---

## 4. DB 스키마 (테이블과 핵심 규칙)

생성 순서: `projects, outline_nodes, writing_cards, departments, resources,
resource_refs, resource_analysis, evidence, drafts, review_opinions,
data_requests, settings`.

- **핵심 보존 규칙**: 목차 노드는 안정적인 `uid`를 가진다. 집필카드·초고·근거는
  **노드 uid에 묶여** 저장 → 목차를 재정렬·개명해도 따라온다. 번호는 저장하지 않고
  렌더 시 계산.
- `resources`: `project_id`(NULL 가능) XOR `dept_id`(공통자료). 자료 변경 시
  `UPDATE evidence SET source_changed=1 WHERE resource_id=?` (참조한 모든 업무에 신호).
- `data_requests`: 상태 필요/요청함/회신옴/반영/보류 + requested_at/due_date/
  received_note/received_resource_id(회신자료를 업무 자료로 등록해 근거로 이음).
- `projects.archived_at`/`archive_note`: **보관함(캐비넷)**. `archived_at`이 비어 있으면 활성.
  값이 있으면 상황판·업무 선택·대시보드 집계에서 빠진다(지워지지 않는다). **삭제는 보관함에
  든 업무만 가능**(`DELETE /api/projects/{pid}`는 활성 업무에 409) → 진행 중인 업무는
  구조적으로 실수 삭제가 안 된다. 삭제해도 공통자료실 자료는 `project_id`가 NULL이라 남는다.
- `settings`: key-value. `author_name`(내 이름), `author_dept`(부서 — 보고전 머리글),
  `inbox_folder`(받은 보고 폴더), `ai.*`(아래).
- `outline_snapshots`: 목차를 통째로 갈아끼우기 **직전** 상태(JSON). `put_outline` 이
  사라지는 항목이 있을 때만 찍는다. 업무당 10개까지. 자세한 규칙은 `services/snapshot.py`.
- `settings` 의 `ai.*` 키: 화면에서 넣은 AI 설정(`ai.OPENAI_API_KEY` 등). `.env` 보다 앞선다.
  등급별 모델: **기본** = `LLM_PROVIDER` + `{OPENAI|ANTHROPIC|GEMINI}_MODEL`(예전 키 그대로 — 기존 설치 호환),
  **빠름·정밀** = `AI_FAST_PROVIDER`·`AI_FAST_MODEL`, `AI_DEEP_PROVIDER`·`AI_DEEP_MODEL`.
  빠름·정밀의 회사가 비면 기본 등급을 통째로 따르고, 모델이 비면 등급별 추천값을 쓴다.
  네 번째 공급자 **호환 서버**(`compat`)는 회사가 아니라 **주소**를 고른다: `ai.COMPAT_BASE_URL`·
  `ai.COMPAT_API_KEY`(없어도 된다)·`ai.COMPAT_MODEL`(추천값이 없어 반드시 적는다).
  자세한 논점은 `docs/design/compat-provider.md`.
- `resources.note`: **담당자 메모**. 자료의 내용(`text`)이 아니라 그 자료를 어떻게 볼지에 대한
  사람의 말이다. 확정 해제·근거 변경신호를 켜지 않고, AI 분석에도 넘기지 않는다.
- `resource_files`: 자료에 올린 **원본 파일**(BLOB) + 읽은 결과 요약. 자료 1건에 파일 1개.
  **`resources` 에 BLOB 컬럼을 두지 않는다** — 자료 목록을 `SELECT *` 로 읽는 곳이 여럿이라
  같은 표에 두면 목록을 부를 때마다 수십 MB 가 딸려 나온다. 목록에 실을 정보는
  `services/attachments.py` 의 `file_meta()` 가 컬럼을 못박아 돌려준다.
  자료를 지우면 `ON DELETE CASCADE` 로 원본도 함께 사라진다.
- `guidelines`: 공모 가이드라인 원본(BLOB) + 읽은 결과 요약 + 마지막 분석(JSON).
  **`resources` 에 넣지 않는다** — 가이드라인은 '근거'가 아니라 '요구사항'이다.
  근거표에 섞이면 `evidence_mark()` 가 무슨 표시를 붙일지 애매해진다.
  공모 한 건에 파일이 여럿 오므로(`doc_kind` = 공고/수립 가이드라인/서식) 업무당 N개.
  원본을 그대로 두는 이유: 정정 공고가 흔하고, 언제든 다시 읽을 수 있어야 한다.
- **마이그레이션 규칙**: `db.py`의 `_migrate()`가 `CREATE TABLE IF NOT EXISTS`
  이후 실행되어 ALTER/재구성으로 구버전 DB를 올린다. **항상 기존 데이터 보존**을
  검증할 것(구스키마 DB를 만들어 테스트). 파괴적 캐스케이드 방지를 위해 테이블
  재구성 시 `PRAGMA foreign_keys=OFF`로 감싼다.

---

## 5. 더 읽을 문서 — 그 일을 할 때만 연다

이 파일에는 **매번 지켜야 할 것**만 둔다. 결정의 경위와 기능별 논점은 `docs/` 로 옮겼다
(줄인 것이 아니라 자리만 옮겼다). **아래 영역을 고치기 전에는 해당 문서를 먼저 읽을 것.**

| 이런 일을 할 때 | 먼저 읽을 문서 |
|---|---|
| 보고전·담당자 진술·보고전 뽑기(`spinoff`)·`family_of` | `docs/design/brief.md` |
| 공모 가이드라인 읽기·분석·배점·정정 공고 (`guideline.py`·`guideline_analysis.py`·`gldiff.py`) | `docs/design/guideline.md` |
| 부서 회신 파일·요청 대조·원본 보관 (`attachments.py`·`resource_analysis.py` 의 `ASKED_RULE`) | `docs/design/reply-files.md` |
| 호환 서버(공통기반 모델)·AI 공급자를 더하기 (`compat_provider.py`·`aiconfig.PROVIDERS`) | `docs/design/compat-provider.md` |
| 주민 설문(구성·정리·분석)·GIS 단계구분도 — **아직 안 만듦, 방향만** | `docs/design/survey.md` |
| 6장 규칙을 바꾸고 싶거나, 왜 그런 규칙인지 알아야 할 때 | `docs/lessons.md` (6장과 같은 소제목) |
| 어떤 기능이 언제·왜 생겼는지, 끝난 할 일 | `docs/history.md` |
| 책 쓰기 플랫폼(별개 제품) 기획 논의 | 별도 저장소 `D:\Desktop\mybooks` 의 `docs/plan.md` (2026-09-12 옮김) |

새 기능의 논점은 이 파일에 길게 붙이지 말고 `docs/design/` 에 새 파일로 두고 위 표에 한 줄을 더한다.
새 교훈은 `docs/lessons.md` 에 경위를 적고, 6장에는 **규칙 한 줄만** 올린다.

---

## 6. 하드-런 규칙 (같은 실수 반복 금지)

규칙만 적는다. 사고 경위는 `docs/lessons.md` 의 **같은 소제목** 아래에 있다.
규칙이 거슬려 바꾸고 싶어지면 반드시 그 경위부터 읽을 것 — 대부분 실제로 데이터를 잃고 세운 것이다.

### 배포·실행 환경
- `.bat` **내용**은 순수 ASCII + CRLF + BOM 없음(한글 *파일명*은 괜찮다). 한글 안내는 `.txt`(UTF-8), `.ps1` 에 한글을 넣으면 UTF-8 **BOM**.
- 패키지를 추가하면 `requirements.txt` 와 `1_SETUP.bat` 의 자가검증 import 목록 **두 곳**을 고친다.
- 임베디드 파이썬엔 tkinter 가 없다 → 폴더 선택창의 PowerShell 대화상자 폴백(`inbox.py`)을 유지한다.
- 포터블 조립은 윈도우에서만 된다(임베디드 파이썬 + win_amd64 휠).
- 포터블 꾸러미에 개발 PC 의 `backend/.env`(키)를 담지 않는다 — 조립 스크립트가 지우고 `.env.example` 로 대신 채운다.
- `frontend/public/사용설명서.html`(담당자용)과 `portable/사용설명.txt`(꾸러미 만들기·반입 — 관리자용)는 대상이 다르니 합치지 말 것.
- `.hwp` 관련은 `services/doc_read.py` 를 고친다. `_hwp_read_prototype.py` 는 import 되지 않는 참고본이다. 제어문자 폭(탭=9)은 줄이지 말 것.
- XML 은 **반드시 `defusedxml`** 로 파싱한다(표준 `xml.etree` 를 import 하지 않는다 — 공공GitLab 보안 스캔이 막는다). 읽기만 안전해지므로 쓰는 쪽은 `_subelement()`·`ET.parse()` 로 둔다. hwpx 접두사(`hp:`)는 유지하지 않아도 한글이 읽는다(실물 확인).
- `requirements.txt` 의 **하한**은 실제로 돌려 본 버전으로 적고, 간접 의존성도 적는다 — 취약점 검사는 하한을 검사한다.

### 한 곳에서만 만든다
- 근거 번호(E-번호) → `services/numbering.py`.
- 목차에 연결된 근거 모으기 → `services/evidence.py` 의 `linked_evidence()`. 근거의 성격을 새로 만들면 `evidence_mark()` 와 함께 본다.
- 목차 틀 → `services/templates.py`. 프런트는 `GET /api/templates` 로 받고 `buildFromTemplate` 하나만 쓴다.
- 목차를 통째로 갈아끼우는 확인 문구 → `App.jsx` 의 `confirmReplace(what)`. **새로 목차를 심는 경로는 반드시 이것을 거친다.**
- 문서 형식 분기 → `services/doc_read.py` 의 `read_document()`. 파일 입구(업무 자료·회신·공통자료)는 모두 `services/attachments.py` 를 부른다.
- 양식 보관함 검사·저장 → `services/formstore.py`. 가이드라인에서 넘겨도 가이드라인 쪽 원본은 지우지 않는다.
- 자료요청 중복 방지 키 → 자동 수집과 `POST /review/{oid}/to-request` 가 같은 `op:{id}` 를 쓴다.
- 대시보드 '막힌 곳'(`_blocked_rows()`)은 새로 세지 않는다 — `compute_metrics` 결과만 모은다.

### 근거·진술 신호
- `source_changed` 는 `POST /evidence/{eid}/acknowledge`('확인함')로만 내린다. 근거 항목을 수정해도 꺼지지 않는다.
- 프로그램이 센 사실(진행상황)도 `STATEMENT_KIND` 자료로 두어 `[진술]` 로 표시한다. `[확정]` 으로 위장시키지 않는다.
- `resources.note`(담당자 메모)는 `changed` 계산에서 빼고, AI 분석에도 넘기지 않는다.

### 목차 파괴 방지·되돌리기
- 보고전은 계획서를 덮어쓰지 않는다 — `POST /projects/{pid}/spinoff` 로 새 업무를 뽑는다(`crossFamily` 면 덮어쓰기를 숨긴다).
- 파괴적 동작의 확인 문구는 사라지는 것을 **전부 세어** 말한다. 새 파괴적 동작엔 미리보기 엔드포인트(`replace-preview`·`delete-preview` 꼴)를 함께 만든다.
- 목차에 매달리는 테이블을 새로 만들면 `put_outline` 의 정리 규칙에 반드시 추가한다.
- `put_outline` 은 **사라지는 항목이 있을 때만** 스냅샷을 찍는다. 되돌리기 자체도 직전 상태를 찍는다.
- 되돌리기는 검토의견은 **사라진 것만** 되살리고, 근거·자료요청은 **끊긴 연결만** 다시 잇는다(`services/snapshot.py`).
- `db.backup_db()` 는 `init_db()`(마이그레이션) **앞에서** 부른다. 백업이 실패해도 앱은 뜬다.

### 문서·파일 읽기
- 확장자를 믿지 않는다 — OLE(`D0CF11E0…`)는 hwp·xls·doc, `PK` 는 hwpx·xlsx·docx 가 겹친다(`_cfb_kind()`·`_zip_kind()`). 못 읽으면 **이유와 방법**을 말한다.
- 행정 시스템의 `.xls` 는 흔히 HTML 표다 → `_looks_html()` + `read_html_table()`. `<style>`/`<script>` 안은 건너뛴다.
- 엑셀은 격자로 읽는다. 병합셀은 hwpx 와 같은 규칙으로 채우고, 날짜·정수 서식은 되돌린다. 본문으로 펼 때 한 줄이 전부 같은 글자면 한 번만 적는다.
- 통째로 빈 열은 버리되(`_drop_empty_cols`), 붙어 있는 같은 값은 묶지 않는다(`0 │ 0 │ 0` 도 수치다).
- 파일에서 읽어 온 본문은 편집 칸에 두지 않는다 — 접어서 읽기만, 사람의 말은 `resources.note` 에.

### 가이드라인
- 배점 ↔ 목차 짝짓기는 확신이 낮으면 낮다고 적고, `card.purpose` 는 덮어쓰지 않고 이어 붙인다(`score_note`).
- 정정 공고 비교는 자동으로 고치지 않는다. 다시 읽지 않고 저장된 분석끼리 견준다.
- 그 밖의 논점(규칙/LLM 역할 분담, 표지 후보군, 읽을 범위)은 `docs/design/guideline.md`.

### 화면(프런트)
- 화면에서 여는 문서·파일은 `frontend/public/` 에 둔다(백엔드 라우트로 내면 개발 서버 5173 에서 빈 화면).
- flex 컨테이너 규칙은 태그별이 아니라 `> *` 로 건다(`.rowbtns>*{flex:1 1 0;min-width:0}`).
- 스크롤은 머리 고정·몸만 스크롤(`.col.pane` + `.pane-head` + `.pane-body`). 선택에 반응하는 버튼은 선택한 것과 함께 보여야 한다.
- 되돌릴 수 없는 버튼 위에서는 드롭다운을 쓰지 않는다(계열 탭 `.famtabs` + 유형 카드 `.tplcard` + 미리보기 `.tpl-peek`). 계열 탭에 별도 상태를 두지 않는다.
- 집필카드 분량은 `card["length"]` 로 읽는다(`card.length` 는 배열 길이처럼 읽힌다).
- `api.js` 의 `req()` 가 FastAPI `detail`(문자열/배열/객체)을 사람이 읽을 문자열로 바꾸는 처리를 유지한다.
- 세 칸 화면의 폭은 `Columns.jsx` 의 `useColumns` 하나로 다룬다(새 세 칸 화면도 이것을 붙인다). 폭은 CSS 변수(`--col-l`/`--col-r`)로만 넘긴다 — 인라인 `grid-template-columns` 는 좁은 화면의 세로 쌓기 규칙을 이겨 버린다. 손잡이는 절대 위치라 그리드 칸 배치(`.rr-err` 1/-1, `.wide-preview` 2/-1)를 건드리지 않는다. 최소 폭은 `LIMITS`·`CENTER_MIN` 과 `styles.css` 의 `minmax` 가 같아야 한다.
- 칸 **폭은 기억하되 접은 상태는 기억하지 않는다** — 다음에 왔을 때 칸이 사라져 있으면 없어진 줄 안다(원칙 5).

### 데이터·용어 설계
- 업무 저장은 부분 업데이트다(보낸 필드만 갱신).
- `projects.status`·`stage` 는 죽은 컬럼이다. 재활용하지 않는다.
- 업무 캐비넷은 '보관/보관함'(`archived`)이다. '보류'는 이미 여러 뜻으로 쓰인다.
- 같은 뜻의 메모 칸을 늘리지 않는다 — 저장은 한 곳, 문만 여럿(회신 등록 뒤엔 `resources.note` 를 띄우고 `PUT /resources/{rid}/note` 로 저장).
- 가리키는 대상이 사라질 수 있는 열은 읽는 쪽에서 확인한다(`received_resource_id` → `received_lost`).
- 목록을 `SELECT *` 로 읽는 표에 BLOB 컬럼을 넣지 않는다(딴 표 + `file_meta()`).

### 서식·AI 설정
- 내보내기 서식도 `family_of` 로 갈린다(`_brief_docx()`). 줄머리(○·-)는 사람이 쓴 것을 그대로 쓰고, 깊이는 들여쓰기에만 쓴다.
- AI 설정은 화면 값(`settings` 의 `ai.*`)이 `.env` 를 이긴다. 화면에 **어느 쪽에서 온 값인지** 표시한다.
- 키 입력칸의 빈 칸은 '그대로 두기', 지우기는 별도 버튼. 연결 시험을 반드시 함께 둔다.
- AI 호출부는 **무슨 일인지(`task=`)만** 말한다. 일→등급 배정은 `aiconfig.TASKS` 한 곳, 등급→회사·모델은 `aiconfig.resolve()` 하나 — 설정 화면의 표시와 실제 호출이 같은 함수를 쓴다. AI 를 부르는 곳을 새로 만들면 `TASKS` 에 한 줄을 더한다.
- 실패해도 다른 등급·회사로 **몰래 넘기지 않는다**(결과에 찍힌 모델 이름이 거짓이 된다). 실패는 그대로 알린다.
- 공급자를 더할 때 **남의 칸을 돌려쓰지 않는다** — 주소만 바꿔 쓰면 결과에 찍히는 회사 이름이 거짓이 된다(`compat`).
  추천 모델을 댈 수 없는 공급자는 `RECOMMENDED` 를 비우고 `model_source` 를 `"없음"` 으로 둔다(짐작한 이름을 '추천값'이라 하지 않는다).
- 작업 화면의 회사 목록은 `api.js` 의 `PROVIDERS` 한 곳에서만 만든다(네 화면이 각자 하드코딩하던 것을 모았다).
- 새 모델 대응은 `providers/base.py` 에서: 온도는 거부당하면 기억해 빼고(`rejected_sampling`), 출력 한도엔 생각 여유(`HEADROOM`)를 더하고, 답은 위치가 아니라 종류로 모은다. 키는 주소에 싣지 않는다(오류 문구에 섞인다).

### 코드 습관·테스트
- 라우트 데코레이터는 **엔드포인트 함수에만** 붙인다(공용 함수 위에 붙어 422 → "[object Object]" 사고).
- 테스트의 TestClient 는 컨텍스트매니저로 쓰지 않아 lifespan 이 안 돈다 → `init_db()` 를 명시 호출. LLM 은 fake provider 로 주입.
- 설정(`ai.*`)을 건드리는 테스트는 **임시 DB** 로 돌린다 — `app.db` import 뒤 `db.DB_PATH`·`db.BACKUP_DIR` 를 갈아끼운다. 실DB로 돌리면 중간에 멈출 때 시험값이 남고, 다음 실행이 그것을 '원래 값'으로 기억해 오염이 굳는다.
- 환경변수를 치우는 것은 `app.main` import **뒤에** 한다(`.env` 가 그때 로드되어 되살아난다 → 실제 API 를 호출해 버린다).

---

## 7. 다음 할 일 (합의된 방향)

> 2026-09-11 정리. v0.21~v0.25 에서 끝난 항목은 `docs/history.md` 의 '끝난 할 일'로 옮겼다.

### 남은 것

**9. 기관 고유 양식 넓히기** — **실물 양식을 모아 안 되는 것부터** 고친다.
   추측으로 넓히지 않는다(양식은 기관마다 다르고, 짐작해 만든 규칙은 다음 양식에서 깨진다).

- 집필카드 안내는 공모사업 계획서·군정기획보고서에만 채웠다. 나머지 유형(용역 과업지시서·
  군수 관심사업·정책검토·간부회의)은 아직 빈 카드다. **빈 카드를 억지로 채우지 말 것** —
  근거 없는 안내문은 없느니만 못하다. 실제로 그 유형을 써 보고 손이 멈추는 자리를 적는다.
- 대시보드에서 심사 배점을 쓰고 싶어지면 그때 `writing_cards.score` 컬럼으로 올린다.

**16. 주민 설문** — 2026-10-13 사용자와 방향을 정함. **챌린지 제출(11.11) 뒤에 시작**한다
   (안내서가 "기능을 넓히기보다 핵심 기능의 안정"을 권한다). 핵심: **설계한 설문지가 곧 분석 틀** —
   계획서의 주장 → 근거 지도(통계로? 설문으로?) → 문항 → 분석 계획을 **수집 전에** 정하고, 구글폼·네이버폼
   내보내기를 설계한 문항에 짝지어 규칙으로 집계한다. **실물 내보내기 파일(구글 1·네이버 1)을 받은 뒤** 시작.
   자세한 것은 `docs/design/survey.md`.

**17. GIS(확장 버전)** — 읍·면별 단계구분도 + 막대그래프. 표준 라이브러리로 SHP 를 읽는 좁은 범위부터.
   설문 다음. `docs/design/survey.md` 끝 '확장 버전'.

### 크게 생각해야 할 것 (전제를 바꾼다)

13. 분업의 다음 단계: 지금은 "보이기"까지. "나눠 하기"(동시편집·권한·서버·실시간)는
    서버를 두지 않는다는 전제를 바꿔야 한다. **정말 필요한지 먼저 확인**하고 별도로.
14. 책 쓰기 플랫폼: **2026-09-11 기획 논의 시작, 2026-09-12 별도 저장소 `D:\Desktop\mybooks` 로 분리**(기획 문서는 그쪽 `docs/plan.md`). 일반 저자 대상, 집필 도구 + 출판사·편집자·독자
    연결 서비스로 **워크벤치와 별개 제품**으로 기획 중이다(예전 메모의 '`doc_type` 하나 더하기'는 대상·배포가 정해지며 폐기).
    원칙 2 는 무의미해지지 않고 모양이 바뀐다 — 논픽션은 출처, 에세이는 저자 진술, 소설은 설정.
15. 화이트라벨(용역업체용 용어/사용자 유형) — 보류. 메뉴 라벨을 한곳에 모아두는 것만 미리.

### 하지 않기로 한 것 (다시 떠오르면 여기를 볼 것)

- **한컴 COM 자동화(pywin32)**: 재현율은 최고지만 설치·등록이 필요 → 행정망에서 못 쓴다.
- **AI가 최종본을 다시 쓰기**: 확정한 본문을 AI가 고치는 순간 다른 물건이 된다(원칙 1).
- **담당자 진술을 LLM 필수로 만들기**: 폴백(줄 단위 쪼개기)을 없애면 '빠른 길'의 명분이 사라진다.
- **목차 틀을 프런트로 되돌리기**: `doc_type` 이 문체까지 가르므로 나뉘면 반드시 어긋난다.
- **헤더 메뉴를 '더보기'로 접기**: 숨겨진 메뉴는 "통제되고 있다는 느낌"의 반대다(원칙 5).
- **가이드라인 읽을 범위를 완전 자동으로**: 조용히 틀린 구간을 읽고도 그럴듯한 결과를
  내놓는 것이 가장 위험하다. 자동 추정은 기본값까지만(`docs/design/guideline.md` 참고).
- **가이드라인을 `resources` 에 넣기**: 요구사항이지 근거가 아니다. 근거표가 흐려진다.
- **파일을 올리자마자 AI 분석까지 자동으로**(v0.21에 사용자와 상의해 정했다): 등록과
  분석은 다른 행위다. 분석은 돈이 들고 실패할 수 있으며, 무엇보다 "이 자료를 근거로
  삼으려 한다"는 사람의 결정과 겹쳐야 한다(원칙 1). 버튼 한 번이 그 자리를 지킨다.

### 정하는 방식

목록을 위에서부터 해치우기보다, **실제 업무 한 건을 처음부터 끝까지** 해 보고
손이 멈추는 자리를 고치는 편이 정확하다. 지금까지 나온 좋은 것(담당자 진술·보고전 뽑기·
헤더 두 줄)은 모두 그렇게 나왔다.

---

## 8. 작업 습관(이 저장소에서 클로드에게)

- 백엔드 변경은 **작은 테스트 스크립트로 검증**하고(엔드포인트 실호출 + 단언),
  마이그레이션은 **구스키마 DB로 데이터 보존까지** 확인한 뒤 마무리한다.
- 프런트 변경은 `npm run build`로 컴파일 통과를 확인한다.
- 사용자는 한국어로 소통한다. 답변·주석·UI 문구는 한국어. 과장 없이, 한 결정의
  **이유**를 짧게 곁들인다.
- 새 기능을 붙이기 전에 **1번(설계 원칙)** 과 충돌하지 않는지 자문한다.
