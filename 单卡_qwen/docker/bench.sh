#!/usr/bin/env bash
# Fixed closed-loop smoke/load benchmark; P4 also requires an open-loop arrival test.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
set -a
source .env
set +a
qwen_target="${1:-backend}"
qwen_concurrency="${2:-1}"
qwen_requests="${3:-200}"
qwen_rate="${4:-inf}"
case "$qwen_target" in
  backend)
    qwen_url=http://vllm:8000
    qwen_model=qwen38-27b
    qwen_key_file=secrets/vllm_api_key
    ;;
  gateway)
    qwen_url=http://new-api:3000
    qwen_model=qwen-27b
    qwen_key_file=secrets/customer_api_key
    ;;
  https)
    [[ "$PUBLIC_DOMAIN" != api.example.com ]] || { echo 'Set PUBLIC_DOMAIN first.' >&2; exit 1; }
    qwen_url="https://${PUBLIC_DOMAIN}"
    qwen_model=qwen-27b
    qwen_key_file=secrets/customer_api_key
    ;;
  *) echo 'Use backend, gateway, or https.' >&2; exit 1 ;;
esac
[[ "$qwen_concurrency" =~ ^[1-9][0-9]*$ && "$qwen_requests" =~ ^[1-9][0-9]*$ ]] || exit 1
IFS= read -r OPENAI_API_KEY < "$qwen_key_file"
export OPENAI_API_KEY
qwen_run="$(date -u +%Y%m%dT%H%M%SZ)-${qwen_target}-c${qwen_concurrency}"
mkdir -p "reports/$qwen_run"
docker run --rm --network qwen27-lab_backend \
  --user "${LOCAL_UID}:${LOCAL_GID}" --env OPENAI_API_KEY \
  --env HF_HUB_OFFLINE=1 --env HF_HUB_CACHE=/reports/hf-cache \
  -v "$PWD/models/nvidia-482ca0f:/model:ro" \
  -v "$PWD/reports/$qwen_run:/reports" \
  --entrypoint vllm "$VLLM_IMAGE" bench serve \
  --backend openai-chat --base-url "$qwen_url" --endpoint /v1/chat/completions \
  --model "$qwen_model" --tokenizer /model --dataset-name random \
  --input-len 1024 --output-len 256 --num-prompts "$qwen_requests" \
  --max-concurrency "$qwen_concurrency" --request-rate "$qwen_rate" \
  --extra-body '{"chat_template_kwargs":{"enable_thinking":false}}' \
  --percentile-metrics ttft,tpot,itl,e2el --metric-percentiles 50,95,99 \
  --save-result --save-detailed --result-dir /reports
