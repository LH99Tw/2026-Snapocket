ROOT_ENV ?=
ifeq ($(strip $(ROOT_ENV)),)
ifneq (,$(wildcard ../.env.$(COMPUTERNAME).local))
ROOT_ENV := ../.env.$(COMPUTERNAME).local
else ifneq (,$(wildcard ../.env.local))
ROOT_ENV := ../.env.local
else ifneq (,$(wildcard ../.env))
ROOT_ENV := ../.env
else
ROOT_ENV :=
endif
endif

ifneq ($(strip $(ROOT_ENV)),)
ifneq (,$(wildcard $(ROOT_ENV)))
include $(ROOT_ENV)
export
endif
endif

AI_AIOPS_PORT ?= 18080
HOST := http://localhost:$(AI_AIOPS_PORT)
AI_AIOPS_SHARED_NETWORK ?= snapocket-shared-net
PYTHON ?= python
SERVICE := aiops-api

COMPOSE_FILES := -f service/docker-compose.aiops.yml
ifeq ($(AI_FORCE_GPU),1)
COMPOSE_FILES += -f service/docker-compose.aiops.gpu.yml
endif

ENV_FILE_ARG :=
ifneq ($(strip $(ROOT_ENV)),)
ifneq (,$(wildcard $(ROOT_ENV)))
ENV_FILE_ARG := --env-file "$(ROOT_ENV)"
endif
endif

COMPOSE := docker compose $(ENV_FILE_ARG) $(COMPOSE_FILES)

BENCH_SCRIPT := service/scripts/bench_v1_infer.py
BENCH_FILE ?= data/testdata/test.png
BENCH_RUNS ?= 20
BENCH_WARMUP ?= 1
BENCH_ENGINE ?= auto
BENCH_TIMEOUT_S ?= 180
BENCH_OUT_DIR ?= data/bench
BENCH_LABEL ?= current
BENCH_OUT ?= $(BENCH_OUT_DIR)/bench-$(BENCH_LABEL)-latest.json

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

BENCH_ACTIVE_ENGINE := paddle
ifeq ($(BENCH_ENGINE),glm)
BENCH_ACTIVE_ENGINE := glm
endif

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo Snapocket AI commands (single entrypoint: ai/Makefile)
	@echo   make up-build   Build/start AI containers
	@echo   make up         Start AI containers
	@echo   make down       Stop and remove container
	@echo   make restart    Restart aiops-api
	@echo   make ps         Show container status
	@echo   make logs       Follow aiops-api logs
	@echo   make logs-tail  Show last 150 lines of logs
	@echo   make shell      Open shell in aiops-api
	@echo   make exec CMD='...'  Run command in aiops-api
	@echo   make health     GET /health/live and /health/ready
	@echo   make status     GET /v1/system/status
	@echo   make bench      Run /v1/infer benchmark
	@echo   make bench-ab-bf16   Run BF16 benchmark scenario
	@echo   make bench-ab-q8     Run Q8 benchmark scenario
	@echo   make bench-compare   Compare benchmark reports
	@echo   make clean-cache     Remove local Python cache files
	@echo   make clean      Down + remove local docker artifacts
	@echo Overrides:
	@echo   AI_FORCE_GPU=1 make up-build   # include gpu compose file
	@echo   ROOT_ENV=../.env.admin.local make up-build

.PHONY: env
env:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "if ([string]::IsNullOrWhiteSpace('$(ROOT_ENV)')) { Write-Host 'ROOT_ENV not set; skip env creation'; exit 0 }; if (Test-Path '$(ROOT_ENV)') { Write-Host '$(ROOT_ENV) already exists'; exit 0 }; $$lines = @('# Root-level env (AI defaults)','AI_AIOPS_PORT=18080','AI_AIOPS_LOCAL_PORT=18081','AI_LLAMA_PORT=18114','AI_LLAMA_LOCAL_PORT=18115','AI_APP_ENV=container','AI_AIOPS_SHARED_NETWORK=snapocket-shared-net','AI_AIOPS_INTERNAL_NETWORK=aiops-net','AI_LLAMA_MODEL_FILE=PaddleOCR-VL-1.5-BF16.gguf','AI_LLAMA_MMPROJ_FILE=mmproj-BF16.gguf','AI_LLAMA_CTX_SIZE=2048','AI_LLAMA_THREADS=8','AI_LLAMA_THREADS_BATCH=8','AI_LLAMA_BATCH_SIZE=1024','AI_LLAMA_UBATCH_SIZE=256','AI_LLAMA_FLASH_ATTN=on','AI_LLAMA_CPUS=6.0','AI_LLAMA_GPU_LAYERS=0','AI_LLAMA_GPU_LAYERS_GPU=99','AI_LLAMACPP_BASE_URL=http://llama-server:8080','AI_LLAMACPP_MODEL_PADDLE=PaddleOCR-VL-1.5-BF16.gguf','AI_LLAMACPP_MODEL_GLM=PaddleOCR-VL-1.5-BF16.gguf','AI_LLAMACPP_REQUEST_TIMEOUT_S=300','AI_LLAMACPP_IMAGE_MAX_SIDE_PX=1024','AI_LLAMACPP_MAX_TOKENS=96','AI_PLAYGROUND_TIMEOUT_S=120'); Set-Content -Path '$(ROOT_ENV)' -Value $$lines -Encoding UTF8; Write-Host '$(ROOT_ENV) created with AI defaults'"
else
	@if [ -z "$(ROOT_ENV)" ]; then \
		echo "ROOT_ENV not set; skip env creation"; \
	elif [ -f "$(ROOT_ENV)" ]; then \
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
			> "$(ROOT_ENV)"; \
		echo "$(ROOT_ENV) created with AI defaults"; \
	fi
endif

.PHONY: network-create
network-create:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "docker network inspect '$(AI_AIOPS_SHARED_NETWORK)' *> $$null; if ($$LASTEXITCODE -ne 0) { docker network create '$(AI_AIOPS_SHARED_NETWORK)' | Out-Null }"
else
	@docker network inspect "$(AI_AIOPS_SHARED_NETWORK)" >/dev/null 2>&1 || docker network create "$(AI_AIOPS_SHARED_NETWORK)"
endif

.PHONY: preflight-port
preflight-port:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "if (@('3000','8000') -contains '$(AI_AIOPS_PORT)') { Write-Host 'AI_AIOPS_PORT=$(AI_AIOPS_PORT) conflicts with FE(3000)/BE(8000).'; Write-Host 'Set AI_AIOPS_PORT to a different host port (example: 18080).'; exit 1 }"
else
	@if [ "$(AI_AIOPS_PORT)" = "3000" ] || [ "$(AI_AIOPS_PORT)" = "8000" ]; then \
		echo "AI_AIOPS_PORT=$(AI_AIOPS_PORT) conflicts with FE(3000)/BE(8000)."; \
		echo "Set AI_AIOPS_PORT to a different host port (example: 18080)."; \
		exit 1; \
	fi
endif

.PHONY: build
build:
	@$(COMPOSE) build

.PHONY: rebuild
rebuild:
	@$(COMPOSE) build --no-cache

.PHONY: up
up: preflight-port network-create env
	@$(COMPOSE) up -d
	@echo "AIOps API: $(HOST)"
	@echo "Ops UI:   $(HOST)/ops"
	@echo "Docs:     $(HOST)/docs"

.PHONY: up-build
up-build: preflight-port network-create env
	@$(COMPOSE) up -d --build
	@echo "AIOps API: $(HOST)"

.PHONY: down
down:
	@$(COMPOSE) down

.PHONY: restart
restart:
	@$(COMPOSE) restart $(SERVICE)

.PHONY: ps
ps:
	@$(COMPOSE) ps

.PHONY: logs
logs:
	@$(COMPOSE) logs -f $(SERVICE)

.PHONY: logs-tail
logs-tail:
	@$(COMPOSE) logs --tail=150 $(SERVICE)

.PHONY: shell
shell:
	@$(COMPOSE) exec $(SERVICE) sh

.PHONY: exec
exec:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "if ([string]::IsNullOrWhiteSpace('$(CMD)')) { Write-Host \"usage: make exec CMD='ls /app'\"; exit 1 }"
else
	@if [ -z "$(CMD)" ]; then \
		echo "usage: make exec CMD='ls /app'"; \
		exit 1; \
	fi
endif
	@$(COMPOSE) exec $(SERVICE) sh -lc "$(CMD)"

.PHONY: health
health:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host '[live]'; (Invoke-RestMethod -Uri '$(HOST)/health/live' -Method Get) | ConvertTo-Json -Depth 20; Write-Host ''; Write-Host '[ready]'; (Invoke-RestMethod -Uri '$(HOST)/health/ready' -Method Get) | ConvertTo-Json -Depth 20"
else
	@echo "[live]"
	@curl -sf "$(HOST)/health/live" | $(PYTHON) -m json.tool
	@echo ""
	@echo "[ready]"
	@curl -sf "$(HOST)/health/ready" | $(PYTHON) -m json.tool
endif

.PHONY: status
status:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "$$headers = @{}; if ('$(AIOPS_API_KEY)' -ne '') { $$headers['x-api-key'] = '$(AIOPS_API_KEY)' }; (Invoke-RestMethod -Uri '$(HOST)/v1/system/status' -Method Get -Headers $$headers) | ConvertTo-Json -Depth 20"
else
	@if [ -n "$(AIOPS_API_KEY)" ]; then \
		curl -sf -H "x-api-key: $(AIOPS_API_KEY)" "$(HOST)/v1/system/status" | $(PYTHON) -m json.tool; \
	else \
		curl -sf "$(HOST)/v1/system/status" | $(PYTHON) -m json.tool; \
	fi
endif

.PHONY: bench
bench:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "New-Item -ItemType Directory -Force -Path '$(BENCH_OUT_DIR)' | Out-Null"
else
	@mkdir -p "$(BENCH_OUT_DIR)"
endif
	@echo "[bench] engine_hint=$(BENCH_ENGINE) ensure_active=$(BENCH_ACTIVE_ENGINE) runs=$(BENCH_RUNS) warmup=$(BENCH_WARMUP)"
	@$(PYTHON) $(BENCH_SCRIPT) run \
		--base-url "$(HOST)" \
		--file "$(BENCH_FILE)" \
		--engine-hint "$(BENCH_ENGINE)" \
		--ensure-active "$(BENCH_ACTIVE_ENGINE)" \
		--runs "$(BENCH_RUNS)" \
		--warmup "$(BENCH_WARMUP)" \
		--timeout-s "$(BENCH_TIMEOUT_S)" \
		--label "$(BENCH_LABEL)" \
		--output "$(BENCH_OUT)" \
		--strict
	@echo "[bench] report=$(BENCH_OUT)"

.PHONY: bench-ab-bf16
bench-ab-bf16:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Test-Path 'model/$(BF16_MODEL)')) { Write-Host 'missing model file: model/$(BF16_MODEL)'; exit 1 }"
else
	@if [ ! -f "model/$(BF16_MODEL)" ]; then \
		echo "missing model file: model/$(BF16_MODEL)"; \
		exit 1; \
	fi
endif
	@$(MAKE) up-build \
		AI_LLAMA_MODEL_FILE=$(BF16_MODEL) \
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
		AI_PLAYGROUND_TIMEOUT_S=$(TUNE_PLAYGROUND_TIMEOUT)
	@$(MAKE) bench BENCH_LABEL=bf16 BENCH_ENGINE=paddle

.PHONY: bench-ab-q8
bench-ab-q8:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Test-Path 'model/$(Q8_MODEL)')) { Write-Host 'missing model file: model/$(Q8_MODEL)'; Write-Host 'download candidate first (e.g. from Hugging Face)'; exit 1 }"
else
	@if [ ! -f "model/$(Q8_MODEL)" ]; then \
		echo "missing model file: model/$(Q8_MODEL)"; \
		echo "download candidate first (e.g. from Hugging Face)"; \
		exit 1; \
	fi
endif
	@$(MAKE) up-build \
		AI_LLAMA_MODEL_FILE=$(Q8_MODEL) \
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
		AI_PLAYGROUND_TIMEOUT_S=$(TUNE_PLAYGROUND_TIMEOUT)
	@$(MAKE) bench BENCH_LABEL=q8 BENCH_ENGINE=paddle

.PHONY: bench-compare
bench-compare:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "if ([string]::IsNullOrWhiteSpace('$(BASELINE)') -or [string]::IsNullOrWhiteSpace('$(CANDIDATE)')) { Write-Host 'usage: make bench-compare BASELINE=data/bench/bench-bf16-*.json CANDIDATE=data/bench/bench-q8-*.json'; exit 1 }"
else
	@if [ -z "$(BASELINE)" ] || [ -z "$(CANDIDATE)" ]; then \
		echo "usage: make bench-compare BASELINE=data/bench/bench-bf16-*.json CANDIDATE=data/bench/bench-q8-*.json"; \
		exit 1; \
	fi
endif
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
	@$(PYTHON) -Bc "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	@$(PYTHON) -Bc "import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"

.PHONY: clean
clean:
	@$(COMPOSE) down --rmi local --remove-orphans
