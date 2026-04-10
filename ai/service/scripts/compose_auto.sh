#!/usr/bin/env bash
set -euo pipefail

BASE_FILE="${BASE_FILE:-docker-compose.aiops.yml}"
GPU_FILE="${GPU_FILE:-docker-compose.aiops.gpu.yml}"

resolve_root_env() {
  if [[ -n "${ROOT_ENV:-}" ]]; then
    printf '%s\n' "$ROOT_ENV"
    return
  fi

  local host="${COMPUTERNAME:-${HOSTNAME:-}}"
  local host_lc=""
  if [[ -n "$host" ]]; then
    host_lc="$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
  fi

  local candidates=()
  if [[ -n "$host_lc" ]]; then
    candidates+=("../../.env.${host_lc}.local")
  fi
  if [[ -n "$host" ]]; then
    candidates+=("../../.env.${host}.local")
  fi
  candidates+=("../../.env.local" "../../.env")

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
}

ROOT_ENV="$(resolve_root_env || true)"

read_env_value() {
  local file="$1"
  local key="$2"
  if [[ ! -f "$file" ]]; then
    return
  fi
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n 1 || true)"
  if [[ -n "$line" ]]; then
    printf '%s' "${line#*=}" | tr -d '\r'
  fi
}

GPU_LAYERS_CPU_DEFAULT="${AI_LLAMA_GPU_LAYERS:-}"
GPU_LAYERS_GPU_DEFAULT="${AI_LLAMA_GPU_LAYERS_GPU:-}"
if [[ -z "$GPU_LAYERS_CPU_DEFAULT" ]] && [[ -n "$ROOT_ENV" ]] && [[ -f "$ROOT_ENV" ]]; then
  GPU_LAYERS_CPU_DEFAULT="$(read_env_value "$ROOT_ENV" "AI_LLAMA_GPU_LAYERS")"
fi
if [[ -z "$GPU_LAYERS_GPU_DEFAULT" ]] && [[ -n "$ROOT_ENV" ]] && [[ -f "$ROOT_ENV" ]]; then
  GPU_LAYERS_GPU_DEFAULT="$(read_env_value "$ROOT_ENV" "AI_LLAMA_GPU_LAYERS_GPU")"
fi
GPU_LAYERS_CPU_DEFAULT="${GPU_LAYERS_CPU_DEFAULT:-0}"
GPU_LAYERS_GPU_DEFAULT="${GPU_LAYERS_GPU_DEFAULT:-99}"

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
if [[ -n "$ROOT_ENV" ]] && [[ -f "$ROOT_ENV" ]]; then
  cmd+=(--env-file "$ROOT_ENV")
  echo "[ai] env file: $ROOT_ENV"
else
  echo "[ai] env file: (none, using process/default values)"
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
