# Snapocket

Next.js (frontend) + FastAPI (backend) — 단일 Docker 이미지로 로컬호스트에서 서비스합니다.

## 포트

| 서비스 | 포트 |
|---|---|
| Next.js | http://localhost:3000 |
| FastAPI | http://localhost:8000 |
| API 문서 (Swagger) | http://localhost:8000/docs |

## 실행 방법

### 프로덕션 (단일 컨테이너)
```bash
docker compose up --build
```

### 로컬 개발 (핫 리로드)
```bash
docker compose --profile dev up --build
```

### AI 컨테이너 (별도 실행, 자동 동시 실행 안 함)
```bash
# 루트에서 AI만 별도 실행
docker compose --profile ai up --build ai-dev
```

`ai` 프로필은 `ai-dev`와 함께 `llama-server` 컨테이너를 실행합니다.

또는

```bash
cd ai
make up-build
```

참고: `docker compose up` 또는 `docker compose --profile dev up`에는 AI 컨테이너가 포함되지 않습니다.

### 직접 실행

**Frontend**
```bash
cd frontend && npm install && npm run dev
```

**Backend**
```bash
cd backend && pip install -r requirements.txt && uvicorn main:app --reload
```

## 브랜치 전략

```
main
├── dev/fe   ← 프론트엔드 작업
└── dev/be   ← 백엔드 작업
```

각 `dev/*` 브랜치에서 작업 후 main 으로 PR을 올립니다.
