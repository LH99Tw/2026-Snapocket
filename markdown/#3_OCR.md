# 3) OCR 튜닝 기록 (llama.cpp + GGUF)

작성일: 2026-04-06 (KST)  
대상: Docker 고정 구조에서 `llama.cpp + GGUF VLM` OCR 지연 개선

## 목표
- 기존 체감: 이미지 1장 약 22초
- 목표: 웜 상태 기준 p95 5초 이내
- 제약: Docker 유지, CPU 경로 기준 우선 최적화

## 이번에 적용한 내용

### 1. 런타임/컴포즈 튜닝
- `llama-server` 기본 실행 옵션 조정
  - `-c 2048`
  - `-t 8`, `-tb 8`
  - `-b 1024`, `-ub 256`
  - `-fa on`
- API 환경변수 추가/반영
  - `LLM_IMAGE_MAX_SIDE_PX=1024`
  - `LLM_MAX_TOKENS=96`
  - `PLAYGROUND_TIMEOUT_S=120`

적용 파일:
- `ai/service/docker-compose.aiops.yml`
- `docker-compose.yml`
- `ai/service/docker-compose.aiops.gpu.yml`

### 2. OCR 요청 페이로드 최적화
- 하드코딩 `max_tokens=256` 제거
- env 기반 `LLM_MAX_TOKENS`(호환: `OLLAMA_MAX_TOKENS`) 사용
- stop 토큰 추가
  - `</s>`
  - `<|end_of_sentence|>`
- 이미지 인코딩 경량화
  - JPEG `quality=82`
  - `optimize=True` 제거

적용 파일:
- `ai/service/backend/app/services/ocr/llamacpp_engine.py`
- `ai/service/backend/app/core/config.py`
- `ai/service/backend/app/services/state.py`
- `ai/service/backend/app/api/v1/system.py`
- `ai/service/backend/app/ops/routes.py`

### 3. Playground 타임아웃 디버깅성 개선
- 클라이언트 Abort timeout(`AbortError`)과 서버 `504`를 분리 표시

적용 파일:
- `ai/service/frontend/templates/ops_playground.html`

### 4. 벤치 자동화 추가
- `/v1/infer` 기준 벤치 스크립트 추가
  - warmup/run 횟수 지정
  - `latency_ms`, `ocr_ms`, `blocks`, `text_len` 수집
  - p50/p95 출력
  - 비교 모드(`compare`)로 속도/품질 게이트 판정
- Make 타깃 추가
  - `bench`
  - `bench-ab-bf16`
  - `bench-ab-q8`
  - `bench-compare`

적용 파일:
- `ai/service/scripts/bench_v1_infer.py`
- `ai/service/Makefile`

## 실측 결과

### A. BF16 + 튜닝 + max_tokens=96 (warmup 1 + run 20)
리포트:
- `ai/data/bench/bench-bf16-tuned-v2-r20-20260406-044817.json`

요약:
- `latency_ms p95 = 6423`
- `ocr_ms p95 = 6262`
- `blocks p50/p95 = 6/6`
- `text_len p50/p95 = 115/115`

판정:
- 목표(`latency p95 <= 5000`, `ocr p95 <= 4500`) 미달

### B. BF16 + max_tokens=80 단기 하한 실험 (warmup 1 + run 3)
리포트:
- `ai/data/bench/bench-bf16-tok80-20260406-044603.json`

요약:
- `latency_ms p95 = 5495`
- `ocr_ms p95 = 5314`

판정:
- 속도는 개선됐지만 5초는 여전히 초과

### C. 품질 비교 게이트 결과
비교 기준:
- baseline: `bench-bf16-tuned-t300-20260406-010150.json`
- candidate: `bench-bf16-tuned-v2-r20-20260406-044817.json`

결과:
- `text_similarity = 0.506608`
- `missing_critical_lines = 4/5`
- `block_ratio = 0.545455`
- 최종 `verdict = false`

## 병목 관찰 (서버 로그 근거)
- 콜드 경로에서 이미지 전처리/인코딩 구간이 매우 큼
  - 예: `image slice encoded in ~250s`
  - 예: `image processed in ~285s`
- 웜 경로는 주로 생성 토큰 시간 지배
  - `96 tokens` eval 대략 `~6.2s`
- 즉, 현재 CPU 경로에서 5초 목표는 매우 타이트함

## 결론
- 계획의 코드/구성 변경은 반영 완료.
- 단, 현재 실측 기준으로는 `5s p95` 목표와 품질 게이트를 동시에 만족하지 못함.
- 추가 의사결정 필요:
  - Q8 모델 확보 후 A/B 실측(`bench-ab-q8`) 진행
  - 또는 GPU 경로/아키텍처 전환 검토

## 추가 보완 (Playground 콜드스타트 체감 이슈 대응)
- 증상:
  - `activate` 이후에도 Playground 첫 요청이 콜드처럼 느려지고 `120000ms` 타임아웃 발생
- 원인:
  - 기존 `activate` warmup은 실질 생성 워밍이 아닌 가용성 probe 수준
- 수정:
  - `LlamaCppVisionEngine.warmup()`에서 실제 멀티모달 1회 생성 워밍 수행(96x96 probe 이미지, `max_tokens=1`)
  - 생성 워밍 상태를 `generation_warm`으로 유지/노출
  - warmup 실패(`False` 또는 예외) 시 activate 자체를 실패 처리
- 검증:
  - activate 호출 응답: `runtime_prepared=true`, 약 42초
  - 직후 Playground 첫 추론: HTTP 200, 약 8초 (타임아웃 미발생)

## 재실행 커맨드
```bash
cd ai/service
make bench
make bench-ab-bf16
make bench-ab-q8
make bench-compare BASELINE=../data/bench/<bf16.json> CANDIDATE=../data/bench/<q8.json>
```
