# 두 PC 에서 작업하는 법 · 행정망 PC 의 제약

> 2026-11-24. 예전 `docs/challenge-2026.md` 에 있던 내용 중 챌린지와 상관없이 계속 쓰는 것만 옮겼다
> (챌린지는 참여하지 않기로 했다).

## 두 PC 에서 작업하는 법

- 행정망 PC 와 집 PC 모두 원격 저장소의 `main` 을 받은 폴더에서 작업한다.
- **시작할 때 `git pull`, 끝낼 때 `commit` + `push`.** push 하지 않고 다른 PC 로 넘어가면 충돌이 난다.
- 원격이 둘이다: `origin` = 공공GitLab, `github` = GitHub. 공공GitLab 은 push 때 보안 스캔
  (Gitleaks·Semgrep·OSV-Scanner·Trivy·Syft)을 통과해야 들어간다(CLAUDE.md 6장 '배포·실행 환경' 규칙).
- Claude 의 작업 메모리는 PC 마다 따로다. 두 PC 가 함께 알아야 할 것은 **이 문서나 CLAUDE.md 에** 적는다.

## 행정망 PC 의 제약 (2026-10-13 확인)

- pypi.org 가 막혀 `pip install` 이 안 된다 → 백엔드를 띄우거나 테스트할 수 없다.
- npm 빌드·GitLab push 는 된다. 한글 2020 이 있다.
- 인터넷이 필요한 일(포터블 꾸러미 조립·모델 구동·백엔드 테스트)은 집 PC 에서 한다.
