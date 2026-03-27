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
