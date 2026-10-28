#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
qwen_gpu_uuid="${1:?Usage: bash init-env.sh GPU-allocated-uuid}"
[[ "$qwen_gpu_uuid" =~ ^GPU-[A-Za-z0-9-]+$ ]] || { echo 'Use one GPU UUID from nvidia-smi.' >&2; exit 1; }
[[ ! -e .env && ! -e secrets/vllm.env ]] || { echo 'Existing configuration found; keep it and edit deliberately.' >&2; exit 1; }
command -v openssl >/dev/null
umask 077
mkdir -p secrets reports backups models/nvidia-482ca0f cache/hf
cp .env.example .env
sed -i "s/^GPU_UUID=.*/GPU_UUID=$qwen_gpu_uuid/; s/^LOCAL_UID=.*/LOCAL_UID=$(id -u)/; s/^LOCAL_GID=.*/LOCAL_GID=$(id -g)/" .env
for qwen_field in POSTGRES_PASSWORD REDIS_PASSWORD SESSION_SECRET GRAFANA_PASSWORD; do
  qwen_random="$(openssl rand -hex 32)"
  sed -i "s/^${qwen_field}=GENERATE$/${qwen_field}=${qwen_random}/" .env
done
qwen_backend_key="$(openssl rand -hex 32)"
printf 'VLLM_API_KEY=%s\n' "$qwen_backend_key" > secrets/vllm.env
printf '%s\n' "$qwen_backend_key" > secrets/vllm_api_key
chmod 600 .env secrets/*
# Container users need to traverse/read these non-secret project directories.
chmod 755 models models/nvidia-482ca0f cache cache/hf reports
echo 'Created .env and protected backend credentials. No service has been started.'
