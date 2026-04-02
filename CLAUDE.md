# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Next.js 16 (App Router) + FastAPI 모노레포. 단일 Docker 이미지로 로컬호스트에서 서비스.

- **Frontend**: `frontend/` — Next.js 16, React 19, TypeScript, Tailwind CSS v4
- **Backend**: `backend/` — FastAPI 0.115, Python 3.12, Pydantic v2
- **포트**: Next.js `3000`, FastAPI `8000`

## 주요 명령어

### 로컬 직접 실행

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && pip install -r requirements.txt && uvicorn main:app --reload
```

### Docker

```bash
# 프로덕션 (단일 컨테이너)
docker compose up --build

# 로컬 개발 (핫 리로드, dev profile)
docker compose --profile dev up --build
```

### Lint

```bash
# Frontend
cd frontend && npm run lint

# Backend (ruff)
cd backend && ruff check .
```

### Git 커밋 템플릿 적용 (최초 1회)

```bash
git config commit.template .github/.gitmessage
```

## 아키텍처

### Docker 단일 이미지 (`Dockerfile`)

멀티스테이지 빌드:

1. `frontend-builder` — Node 20 Alpine에서 `npm run build` 실행, `.next/standalone` 생성
2. `runtime` — Python 3.12-slim 기반, Node.js 추가 설치 후 FastAPI + Next.js standalone 동시 구동
3. `docker-entrypoint.sh`가 uvicorn(8000)과 `node server.js`(3000)를 백그라운드로 실행

`next.config.ts`에 `output: "standalone"` 설정이 필수 — 없으면 Docker 이미지에서 Next.js가 동작하지 않음.

### Next.js App Router 구조

`frontend/app/` 아래 파일 기반 라우팅. `layout.tsx`가 루트 레이아웃, `page.tsx`가 각 경로의 진입점.

### FastAPI 구조

`backend/main.py`가 앱 진입점. CORS는 `http://localhost:3000`만 허용(개발 환경). 라우터 추가 시 `app.include_router()`로 등록.

## Git 워크플로우

### 브랜치 전략

```
main
├── dev/fe   ← 프론트엔드 작업
└── dev/be   ← 백엔드 작업
```

`dev/*` 브랜치에서 작업 후 `main`으로 PR. CI가 PR 시 자동 검증(lint → build → Docker build).

### 커밋 컨벤션

**형식**: `타입: <한줄_요약> (#이슈번호)`

상세 설명이 있으면 `!` 추가: `타입!: <요약> (#번호)`

| 타입       | 용도                           |
| ---------- | ------------------------------ |
| `feat`     | 새로운 기능 추가               |
| `fix`      | 버그 수정                      |
| `refactor` | 코드 리팩토링                  |
| `design`   | CSS 등 UI 디자인 변경          |
| `style`    | 코드 포맷팅, 세미콜론 등       |
| `setting`  | 프로젝트 설정 관련             |
| `docs`     | 문서 수정                      |
| `cicd`     | CI/CD 및 빌드 관련             |
| `chore`    | 빌드, 패키지 매니저, 기타 업무 |

커밋 메시지에 Claude 관련 내용(`🤖 Generated with [Claude Code]`, `Co-Authored-By: Claude` 등) 포함 금지.
