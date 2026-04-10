# AI Service

실행/운영 커맨드는 `ai/Makefile` 단일 진입점으로 관리합니다.

## 실행
```bash
cd ai
make up-build
```

자주 쓰는 명령:
```bash
make ps
make logs
make down
```

## 런타임
- OCR 추론 백엔드는 `llama.cpp server` 전용입니다.
- 기본 연결: `LLM_BASE_URL=http://llama-server:8080`
- 기본 모델:
  - `LLM_MODEL_PADDLE=PaddleOCR-VL-1.5-BF16.gguf`
  - `LLM_MODEL_GLM=PaddleOCR-VL-1.5-BF16.gguf`
- 성능 튜닝 기본값:
  - `LLM_MAX_TOKENS=96`
  - `LLM_IMAGE_MAX_SIDE_PX=1024`
  - `PLAYGROUND_TIMEOUT_S=120`

## 구성
- backend: `service/backend/app`
- frontend assets/templates: `service/frontend`
- compose: `service/docker-compose.aiops.yml`
