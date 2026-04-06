COMPOSE_FILE := docker-compose.aiops.yml
COMPOSE_GPU_FILE := docker-compose.aiops.gpu.yml
COMPOSE_AUTO := ./scripts/compose_auto.sh
ROOT_ENV := ../../.env
SERVICE := aiops-api

ifneq (,$(wildcard $(ROOT_ENV)))
include $(ROOT_ENV)
export
endif

AI_AIOPS_PORT ?= 18080
HOST := http://localhost:$(AI_AIOPS_PORT)
AI_AIOPS_SHARED_NETWORK ?= snapocket-shared-net
PYTHON ?= python3
BENCH_SCRIPT := scripts/bench_v1_infer.py
BENCH_FILE ?= ../data/testdata/test.png
BENCH_RUNS ?= 20
BENCH_WARMUP ?= 1
BENCH_ENGINE ?= auto
BENCH_TIMEOUT_S ?= 180
BENCH_OUT_DIR ?= ../data/bench
BENCH_LABEL ?= current
BF16_MODEL ?= PaddleOCR-VL-1.5-BF16.gguf
Q8_MODEL ?= PaddleOCR-VL-1.5-Q8_0.gguf
MMPROJ_MODEL ?= mmproj-BF16.gguf
TUNE_CTX ?= 2048
TUNE_THREADS ?= 8
TUNE_THREADS_BATCH ?= 8
TUNE_BATCH ?= 1024
TUNE_UBATCH ?= 256
TUNE_FLASH_ATTN ?= on
TUNE_IMAGE_MAX_SIDE ?= 1024
TUNE_MAX_TOKENS ?= 96
TUNE_PLAYGROUND_TIMEOUT ?= 120

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "Snapocket AI container commands"
	@echo ""
	@echo "  env             Ensure root .env exists (create minimal defaults if missing)"
	@echo "  network-create  Create shared docker network for BE/FE<->AI communication"
	@echo "  preflight-port  Validate AI host port does not overlap FE/BE reserved ports"
	@echo "  build           Build aiops-api image (auto GPU detect)"
	@echo "  rebuild         Rebuild image without cache (auto GPU detect)"
	@echo "  up              Start aiops-api container (auto GPU detect)"
	@echo "  up-build        Build and start aiops-api container (auto GPU detect)"
	@echo "  down            Stop and remove container"
	@echo "  restart         Restart aiops-api"
	@echo "  ps              Show container status"
	@echo "  logs            Follow aiops-api logs"
	@echo "  logs-tail       Show last 150 lines of logs"
	@echo "  shell           Open shell in aiops-api"
	@echo "  exec CMD='...'  Run command in aiops-api"
	@echo "  health          GET /health/live and /health/ready"
	@echo "  status          GET /v1/system/status"
	@echo "  bench           Run /v1/infer benchmark (warmup 1 + runs 20)"
	@echo "  bench-ab-bf16   Switch runtime to BF16 model and benchmark"
	@echo "  bench-ab-q8     Switch runtime to Q8 model and benchmark"
	@echo "  bench-compare   Compare BF16 vs Q8 benchmark reports"
	@echo "  clean-cache     Remove local Python cache files"
	@echo "  clean           Down + remove local docker artifacts"
	@echo ""
	@echo "Overrides:"
	@echo "  AI_FORCE_GPU=1 make up-build  # force GPU mode"
	@echo "  AI_FORCE_GPU=0 make up-build  # force CPU mode"

.PHONY: env
env:
	@if [ -f $(ROOT_ENV) ]; then \
		echo "$(ROOT_ENV) already exists"; \
	else \
		printf '%s\n' \
			'# Root-level env (AI defaults)' \
			'AI_AIOPS_PORT=18080' \
			'AI_AIOPS_LOCAL_PORT=18081' \
			'AI_LLAMA_PORT=18114' \
			'AI_LLAMA_LOCAL_PORT=18115' \
			'AI_APP_ENV=container' \
			'AI_AIOPS_SHARED_NETWORK=snapocket-shared-net' \
			'AI_AIOPS_INTERNAL_NETWORK=aiops-net' \
			'AI_LLAMA_MODEL_FILE=PaddleOCR-VL-1.5-BF16.gguf' \
			'AI_LLAMA_MMPROJ_FILE=mmproj-BF16.gguf' \
			'AI_LLAMA_CTX_SIZE=2048' \
			'AI_LLAMA_THREADS=8' \
			'AI_LLAMA_THREADS_BATCH=8' \
			'AI_LLAMA_BATCH_SIZE=1024' \
			'AI_LLAMA_UBATCH_SIZE=256' \
			'AI_LLAMA_FLASH_ATTN=on' \
			'AI_LLAMA_CPUS=6.0' \
			'AI_LLAMA_GPU_LAYERS=0' \
			'AI_LLAMA_GPU_LAYERS_GPU=99' \
			'AI_LLAMACPP_BASE_URL=http://llama-server:8080' \
			'AI_LLAMACPP_MODEL_PADDLE=PaddleOCR-VL-1.5-BF16.gguf' \
			'AI_LLAMACPP_MODEL_GLM=PaddleOCR-VL-1.5-BF16.gguf' \
			'AI_LLAMACPP_REQUEST_TIMEOUT_S=300' \
			'AI_LLAMACPP_IMAGE_MAX_SIDE_PX=1024' \
			'AI_LLAMACPP_MAX_TOKENS=96' \
			'AI_PLAYGROUND_TIMEOUT_S=120' \
			> $(ROOT_ENV); \
			echo "$(ROOT_ENV) created with AI defaults"; \
		fi

.PHONY: network-create
network-create:
	@docker network inspect $(AI_AIOPS_SHARED_NETWORK) >/dev/null 2>&1 || docker network create $(AI_AIOPS_SHARED_NETWORK)

.PHONY: preflight-port
preflight-port:
	@case "$(AI_AIOPS_PORT)" in \
		3000|8000) \
			echo "AI_AIOPS_PORT=$(AI_AIOPS_PORT) conflicts with FE(3000)/BE(8000)."; \
			echo "Set AI_AIOPS_PORT to a different host port (example: 18080)."; \
			exit 1 ;; \
		*) ;; \
	esac

.PHONY: build
build:
	$(COMPOSE_AUTO) build

.PHONY: rebuild
rebuild:
	$(COMPOSE_AUTO) build --no-cache

.PHONY: up
up: preflight-port network-create env
	$(COMPOSE_AUTO) up -d
	@echo "AIOps API: $(HOST)"
	@echo "Ops UI:   $(HOST)/ops"
	@echo "Docs:     $(HOST)/docs"

.PHONY: up-build
up-build: preflight-port network-create env
	$(COMPOSE_AUTO) up -d --build
	@echo "AIOps API: $(HOST)"

.PHONY: down
down:
	$(COMPOSE_AUTO) down

.PHONY: restart
restart:
	$(COMPOSE_AUTO) restart $(SERVICE)

.PHONY: ps
ps:
	$(COMPOSE_AUTO) ps

.PHONY: logs
logs:
	$(COMPOSE_AUTO) logs -f $(SERVICE)

.PHONY: logs-tail
logs-tail:
	$(COMPOSE_AUTO) logs --tail=150 $(SERVICE)

.PHONY: shell
shell:
	$(COMPOSE_AUTO) exec $(SERVICE) sh

.PHONY: exec
exec:
	@if [ -z "$(CMD)" ]; then \
		echo "usage: make exec CMD='ls /app'"; \
		exit 1; \
	fi
	$(COMPOSE_AUTO) exec $(SERVICE) sh -lc "$(CMD)"

.PHONY: health
health:
	@echo "[live]"
	@curl -sf $(HOST)/health/live | $(PYTHON) -m json.tool
	@echo ""
	@echo "[ready]"
	@curl -sf $(HOST)/health/ready | $(PYTHON) -m json.tool

.PHONY: status
status:
	@curl -sf $(HOST)/v1/system/status | $(PYTHON) -m json.tool

.PHONY: bench
bench:
	@mkdir -p $(BENCH_OUT_DIR)
	@set -e; \
		ENGINE=$$( [ "$(BENCH_ENGINE)" = "glm" ] && echo "glm" || echo "paddle" ); \
		STAMP=$$(date +%Y%m%d-%H%M%S); \
		OUT="$(BENCH_OUT_DIR)/bench-$(BENCH_LABEL)-$$STAMP.json"; \
		echo "[bench] engine_hint=$(BENCH_ENGINE) ensure_active=$$ENGINE runs=$(BENCH_RUNS) warmup=$(BENCH_WARMUP)"; \
		$(PYTHON) $(BENCH_SCRIPT) run \
			--base-url $(HOST) \
			--file $(BENCH_FILE) \
			--engine-hint $(BENCH_ENGINE) \
			--ensure-active $$ENGINE \
			--runs $(BENCH_RUNS) \
			--warmup $(BENCH_WARMUP) \
			--timeout-s $(BENCH_TIMEOUT_S) \
			--label "$(BENCH_LABEL)" \
			--output "$$OUT" \
			--strict; \
		echo "[bench] report=$$OUT"

.PHONY: bench-ab-bf16
bench-ab-bf16:
	@if [ ! -f ../model/$(BF16_MODEL) ]; then \
		echo "missing model file: ../model/$(BF16_MODEL)"; \
		exit 1; \
	fi
	@AI_LLAMA_MODEL_FILE=$(BF16_MODEL) \
	AI_LLAMA_MMPROJ_FILE=$(MMPROJ_MODEL) \
	AI_LLAMA_CTX_SIZE=$(TUNE_CTX) \
	AI_LLAMA_THREADS=$(TUNE_THREADS) \
	AI_LLAMA_THREADS_BATCH=$(TUNE_THREADS_BATCH) \
	AI_LLAMA_BATCH_SIZE=$(TUNE_BATCH) \
	AI_LLAMA_UBATCH_SIZE=$(TUNE_UBATCH) \
	AI_LLAMA_FLASH_ATTN=$(TUNE_FLASH_ATTN) \
	AI_LLAMACPP_MODEL_PADDLE=$(BF16_MODEL) \
	AI_LLAMACPP_MODEL_GLM=$(BF16_MODEL) \
	AI_LLAMACPP_IMAGE_MAX_SIDE_PX=$(TUNE_IMAGE_MAX_SIDE) \
	AI_LLAMACPP_MAX_TOKENS=$(TUNE_MAX_TOKENS) \
	AI_PLAYGROUND_TIMEOUT_S=$(TUNE_PLAYGROUND_TIMEOUT) \
	$(COMPOSE_AUTO) up -d --force-recreate llama-server aiops-api
	@$(MAKE) bench BENCH_LABEL=bf16 BENCH_ENGINE=paddle

.PHONY: bench-ab-q8
bench-ab-q8:
	@if [ ! -f ../model/$(Q8_MODEL) ]; then \
		echo "missing model file: ../model/$(Q8_MODEL)"; \
		echo "download candidate first (e.g. from Hugging Face)"; \
		exit 1; \
	fi
	@AI_LLAMA_MODEL_FILE=$(Q8_MODEL) \
	AI_LLAMA_MMPROJ_FILE=$(MMPROJ_MODEL) \
	AI_LLAMA_CTX_SIZE=$(TUNE_CTX) \
	AI_LLAMA_THREADS=$(TUNE_THREADS) \
	AI_LLAMA_THREADS_BATCH=$(TUNE_THREADS_BATCH) \
	AI_LLAMA_BATCH_SIZE=$(TUNE_BATCH) \
	AI_LLAMA_UBATCH_SIZE=$(TUNE_UBATCH) \
	AI_LLAMA_FLASH_ATTN=$(TUNE_FLASH_ATTN) \
	AI_LLAMACPP_MODEL_PADDLE=$(Q8_MODEL) \
	AI_LLAMACPP_MODEL_GLM=$(Q8_MODEL) \
	AI_LLAMACPP_IMAGE_MAX_SIDE_PX=$(TUNE_IMAGE_MAX_SIDE) \
	AI_LLAMACPP_MAX_TOKENS=$(TUNE_MAX_TOKENS) \
	AI_PLAYGROUND_TIMEOUT_S=$(TUNE_PLAYGROUND_TIMEOUT) \
	$(COMPOSE_AUTO) up -d --force-recreate llama-server aiops-api
	@$(MAKE) bench BENCH_LABEL=q8 BENCH_ENGINE=paddle

.PHONY: bench-compare
bench-compare:
	@if [ -z "$(BASELINE)" ] || [ -z "$(CANDIDATE)" ]; then \
		echo "usage: make bench-compare BASELINE=../data/bench/bench-bf16-*.json CANDIDATE=../data/bench/bench-q8-*.json"; \
		exit 1; \
	fi
	@$(PYTHON) $(BENCH_SCRIPT) compare \
		--baseline "$(BASELINE)" \
		--candidate "$(CANDIDATE)" \
		--target-p95-ms 5000 \
		--target-ocr-p95-ms 4500 \
		--min-similarity 0.95 \
		--critical-line-similarity 0.75 \
		--min-block-ratio 0.8

.PHONY: clean-cache
clean-cache:
	$(PYTHON) -Bc "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -Bc "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"

.PHONY: clean
clean:
	$(COMPOSE_AUTO) down --rmi local --remove-orphans
