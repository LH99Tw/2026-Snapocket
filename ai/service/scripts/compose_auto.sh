#!/usr/bin/env bash
set -euo pipefail

ROOT_ENV="${ROOT_ENV:-../../.env}"
BASE_FILE="${BASE_FILE:-docker-compose.aiops.yml}"
GPU_FILE="${GPU_FILE:-docker-compose.aiops.gpu.yml}"
GPU_LAYERS_CPU_DEFAULT="${AI_LLAMA_GPU_LAYERS:-0}"
GPU_LAYERS_GPU_DEFAULT="${AI_LLAMA_GPU_LAYERS_GPU:-99}"

use_gpu=0
if [[ "${AI_FORCE_GPU:-auto}" == "1" ]]; then
  use_gpu=1
elif [[ "${AI_FORCE_GPU:-auto}" == "0" ]]; then
  use_gpu=0
elif [[ -f "$GPU_FILE" ]] && command -v nvidia-smi >/dev/null 2>&1; then
  if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi "nvidia"; then
    use_gpu=1
  fi
fi

cmd=(docker compose)
if [[ -f "$ROOT_ENV" ]]; then
  cmd+=(--env-file "$ROOT_ENV")
fi
cmd+=(-f "$BASE_FILE")

if [[ "$use_gpu" -eq 1 ]]; then
  cmd+=(-f "$GPU_FILE")
  export AI_LLAMA_GPU_LAYERS="$GPU_LAYERS_GPU_DEFAULT"
  echo "[ai] GPU mode enabled (AI_LLAMA_GPU_LAYERS=${AI_LLAMA_GPU_LAYERS})"
else
  export AI_LLAMA_GPU_LAYERS="$GPU_LAYERS_CPU_DEFAULT"
  echo "[ai] CPU mode enabled (AI_LLAMA_GPU_LAYERS=${AI_LLAMA_GPU_LAYERS})"
fi

exec "${cmd[@]}" "$@"
