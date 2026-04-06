# AI Service

실행 기준 폴더: `ai/service`

## 실행
```bash
make up-build
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
