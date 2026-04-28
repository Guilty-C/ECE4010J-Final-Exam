#!/usr/bin/env bash
# ops/download_qwen.sh — Phase H6 (run when starting Phase I, not earlier).
#
# Downloads Qwen/Qwen2.5-3B-Instruct (~6 GB, BF16 safetensors) into the
# remote HF cache. The cache root on ivlab is symlinked from
# ~/.cache/huggingface/hub -> /data2/lrrelevant/hf_offline/hub, so the
# download lands on /data2 automatically and does NOT touch the
# 98%-full root partition.
#
# Idempotent: if the snapshot already exists locally, huggingface_hub
# only verifies file hashes.
#
# Networking: huggingface.co is unreachable from ivlab (DNS blocked), so
# we route huggingface_hub through hf-mirror.com via HF_ENDPOINT. Phase B
# already used the same mirror for the Hendrycks parquet.
#
# Usage:
#   bash ops/download_qwen.sh
#   REMOTE=remote-gpu MODEL=Qwen/Qwen2.5-3B-Instruct bash ops/download_qwen.sh
set -euo pipefail
REMOTE="${REMOTE:-ivlab}"
MODEL="${MODEL:-Qwen/Qwen2.5-3B-Instruct}"
ENV_NAME="${ENV_NAME:-agentiad}"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

ssh -o BatchMode=yes "$REMOTE" "MODEL='$MODEL' ENV_NAME='$ENV_NAME' HF_ENDPOINT='$HF_ENDPOINT' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
PY="$HOME/miniconda3/envs/$ENV_NAME/bin/python"
if [ ! -x "$PY" ]; then
  echo "FAIL: conda env '$ENV_NAME' python not at $PY" >&2; exit 1
fi
echo "[dl] using $PY (HF_ENDPOINT=$HF_ENDPOINT)"
export HF_ENDPOINT
"$PY" -c "from huggingface_hub import snapshot_download; \
p = snapshot_download(repo_id='${MODEL}', local_files_only=False); \
print('snapshot at', p)"
REMOTE_SCRIPT
