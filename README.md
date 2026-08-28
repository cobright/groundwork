# AI 행정기획 워크벤치

한국 지방자치단체(군청) 기획 담당자의 **행정문서 작성 전 과정**
(자료조사 → 초고 → 검토 → 최종본)을 표준화해 돕는 **로컬 단일 사용자 도구**.
FastAPI + React(Vite) + SQLite.

> **개발을 이어받는 분(사람/클로드)은 먼저 [`CLAUDE.md`](./CLAUDE.md)를 읽으세요.**
> 설계 원칙·구조·지금까지의 결정·주의사항이 모두 거기 있습니다.
> 그 원칙과 충돌하는 변경은 하지 않습니다.

## 빠른 시작 (개발 PC)

필요: Python 3.11+, Node.js 18+

```
# 백엔드
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # (mac/linux: .venv/bin/pip)
copy .env.example .env                              # 필요한 provider 키만 채움
python run.py                                       # http://127.0.0.1:8000 (API + 빌드된 프런트)

# 프런트(개발서버, 별도 터미널)
cd frontend
npm install
npm run dev                                         # http://localhost:5173 (/api → 8000 프록시)
```

Windows에서는 `1_SETUP.bat`(최초 1회) → `2_START.bat`(두 창 실행)도 사용 가능.

## 배포 (행정망, 설치 없이)

`portable/포터블_만들기.bat`를 **인터넷 되는 윈도우 PC**에서 1회 실행 →
`행정기획워크벤치_포터블` 폴더 생성 → 행정망 PC로 반입 → `실행.bat` 더블클릭.
자세한 내용은 `portable/사용설명.txt`.

## 구조 한눈에

- `backend/app/main.py` FastAPI 진입점(+ 빌드된 프런트 서빙)
- `backend/app/db.py` SQLite 스키마·마이그레이션(목차 uid에 카드/근거를 묶어 보존)
- `backend/app/routers/` projects·outline·resources·library·review·requests·
  export·dashboard·report·inbox
- `backend/app/providers/` LLM 어댑터(openai/claude/gemini, registry로 교체)
- `backend/app/agents/` 검토 서브에이전트(사실확인·기술·구조·비평)
- `frontend/src/` React 화면(App + 각 Room + Dashboard/Inbox/ReportModal)

자세한 설계 맥락은 **`CLAUDE.md`**.
