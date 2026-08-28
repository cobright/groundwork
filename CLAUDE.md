# CLAUDE.md — AI 행정기획 워크벤치 인수인계

이 문서는 이 저장소에서 **Claude Code(또는 다른 클로드)** 가 작업을 이어갈 때
가장 먼저 읽어야 하는 문서입니다. 이 도구가 무엇이고, 왜 이렇게 설계됐으며,
무엇을 건드리면 안 되는지를 담았습니다. **코드를 바꾸기 전에 이 문서의 원칙을
먼저 지키세요.** 원칙과 충돌하는 "개선"은 개선이 아닙니다.

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

4. **로컬·설치 최소.** 행정망은 설치가 어렵다 → 포터블(설치 없이 실행)을 목표로 한다.
   외부 서버·클라우드에 의존하지 않는다. 데이터는 로컬 SQLite 한 파일.

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
    providers/           LLM 어댑터: base + openai/claude/gemini + registry(교체)
    agents/              검토 서브에이전트: fact_check(사실확인), technical(기술),
                         structure(구조), critique(비평) + common(공용 파싱/조립)
    skills/              반복작업 표준절차: resource_analysis, draft_writing
    services/            export_docx.py (.docx 조립: 맑은 고딕 + 근거 부록)
frontend/src/
  App.jsx                헤더(지휘 바)+탭 라우팅. 뷰: dashboard/inbox/outline/
                         resources/library/draft/review/requests/final
  api.js                 모든 API 호출 헬퍼(+ reportApi). 오류 detail 안전 포맷.
  outlineModel.js        목차 트리/카드 로직(번호는 렌더 시 계산)
  Dashboard.jsx          초기화면. 업무 카드(결재란 단계 띠 + 미해결 칩 + 마감).
  ResourceRoom / LibraryRoom / DraftRoom / ReviewRoom / RequestRoom /
  FinalRoom / InboxRoom / ReportModal.jsx
  styles.css             상황실 톤 디자인 토큰(:root) + 전 화면 스타일
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
- `settings`: key-value. `author_name`(내 이름), `inbox_folder`(받은 보고 폴더).
- **마이그레이션 규칙**: `db.py`의 `_migrate()`가 `CREATE TABLE IF NOT EXISTS`
  이후 실행되어 ALTER/재구성으로 구버전 DB를 올린다. **항상 기존 데이터 보존**을
  검증할 것(구스키마 DB를 만들어 테스트). 파괴적 캐스케이드 방지를 위해 테이블
  재구성 시 `PRAGMA foreign_keys=OFF`로 감싼다.

---

## 5. 지금까지의 버전 흐름 (무엇을 왜 했는가)

v0.1~0.7 기초: 목차 → 자료+AI분석+근거표 → 자료수정 → AI초고 → 사실확인검토 →
검토자완성(기술·구조·비평) → 최종본(.docx).
v0.8~0.9 공통자료실: 부서 폴더 + 단순 참조(스냅샷 아님) + 승격(업무자료→공통).
v0.10~0.11 부서 자료요청서: 수집(초고 [확인 필요] + 검토 필요조치, 중복방지) +
부서배정 + 상태관리 + 발송/마감/회신자료 등록 + xlsx(부서별 시트).
v0.12 대시보드: 업무 가로지르는 집계 + 업무 마감일(부분수정으로 필드보존).
v0.13 대시보드 홈 + 외형('상황실' 톤, 결재란 단계 띠).
v0.14 진행상황 보고 ①: 보고 팝업(자동사실 읽기전용 + 사람 한마디) + 내 이름 설정 +
보고파일(JSON: 기계용 구조 + 사람용 human_summary).
v0.15 받은 보고 ②: 폴더의 보고파일을 읽어 (보고자·업무)별 최신만, 업무별/팀원별 보기.
v0.16 폴더 선택창(pick-folder).
v0.17 포터블 배포 준비(설치 없이 행정망 실행).

---

## 6. 하드-런 교훈(같은 실수 반복 금지)

- **`.bat` 파일 내용은 순수 ASCII + CRLF + BOM 없음.** 한글을 .bat *내용*에 넣으면
  cmd가 깨진다(한글 *파일명*은 괜찮다). 한글 안내는 `.txt`(UTF-8)에 둔다.
  PowerShell `.ps1`에 한글을 넣을 땐 UTF-8 **BOM** 저장.
- **부분 업데이트**: 업무 저장 시 보낸 필드만 갱신. 예전에 이름만 바꿔도 목적·대상·
  마감이 지워지던 버그가 있었다. (projects.py는 이제 부분수정)
- **라우트 데코레이터 위치 주의**: 집계 로직을 함수로 뺄 때 `@router.get("/dashboard")`
  가 실수로 `compute_metrics(c,p)` 위에 붙어, FastAPI가 c·p를 쿼리 파라미터로
  요구해 422 → 프런트에 "[object Object]"로 표시된 사고가 있었다. 데코레이터는
  **엔드포인트 함수에만**.
- **오류 표시**: `api.js`의 `req()`는 FastAPI의 `detail`이 문자열/배열/객체 어느
  것이어도 사람이 읽을 문자열로 변환한다. 유지할 것.
- **테스트 방식**: TestClient는 컨텍스트매니저로 쓰지 않으므로 lifespan이 안 돈다 →
  테스트에서 `init_db()`를 명시 호출. LLM은 fake provider로 주입해 검증.
- **임베디드 파이썬엔 tkinter가 없다** → 폴더 선택창은 tkinter 실패 시 윈도우
  PowerShell 폴더 대화상자로 폴백(inbox.py). 둘 다 안 되면 직접 입력.
- **포터블 조립은 윈도우에서** 실행된다(임베디드 파이썬 + win_amd64 휠). 리눅스
  개발환경에서 최종 꾸러미를 만들 수 없다.

---

## 7. 다음 할 일 (합의된 방향)

1. **HWPX 양식 채우기** (가장 큰 다음 과제).
   - 사용자가 제공하는 **실제 계획서 .hwpx 양식에는 `{{치환표시}}`가 없다.**
     따라서 치환표시 방식은 **폐기**. 양식의 **구조(장·절·표·빈칸)를 읽어**
     알맞은 자리에 최종본을 자동으로 넣어야 한다(양식마다 구조가 달라 어렵다 →
     제대로 된 시간을 들여야 함).
   - HWPX = XML을 담은 ZIP. 파이썬 표준(zipfile + XML)으로 새 라이브러리 없이 가능.
   - **서버(파이썬)가 하는 일** → 포터블 방식과 잘 맞는다. 배포가 선 결정된 지금
     착수 적기. 사용자 스킬 `hwpx-autofill-conversion`(있다면)과 방향 일치.
2. 분업의 **다음 단계**(정말 필요할 때): 지금은 "보이기"까지. "나눠 하기"(다중
   사용자·권한·서버·실시간)는 전제를 바꾸는 큰 과제 → 신중히, 별도로.
3. 화이트라벨(용역업체용 용어/사용자 유형) — 보류 중.

---

## 8. 작업 습관(이 저장소에서 클로드에게)

- 백엔드 변경은 **작은 테스트 스크립트로 검증**하고(엔드포인트 실호출 + 단언),
  마이그레이션은 **구스키마 DB로 데이터 보존까지** 확인한 뒤 마무리한다.
- 프런트 변경은 `npm run build`로 컴파일 통과를 확인한다.
- 사용자는 한국어로 소통한다. 답변·주석·UI 문구는 한국어. 과장 없이, 한 결정의
  **이유**를 짧게 곁들인다.
- 새 기능을 붙이기 전에 **1번(설계 원칙)** 과 충돌하지 않는지 자문한다.
