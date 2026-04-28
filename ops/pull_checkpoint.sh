#!/usr/bin/env bash
# ops/pull_checkpoint.sh — Phase I→J handoff.
#
# Pulls a LoRA adapter checkpoint produced by remote training back into
# the local checkpoints/ directory via rsync over SSH. Skips
# regenerable training-state blobs (optimizer.pt, scheduler.pt,
# global_step*/) per .gitignore.
#
# Usage:
#   bash ops/pull_checkpoint.sh                        # default name
#   bash ops/pull_checkpoint.sh qwen25_3b_lora_v1
#   REMOTE=remote-gpu REMOTE_ROOT=/data2/lrrelevant/ve401-solver \
#       bash ops/pull_checkpoint.sh qwen25_3b_lora_v2
set -euo pipefail
REMOTE="${REMOTE:-ivlab}"
REMOTE_ROOT="${REMOTE_ROOT:-/data2/lrrelevant/ve401-solver}"
NAME="${1:-qwen25_3b_lora_v1}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)/checkpoints/$NAME"

mkdir -p "$LOCAL_DIR"
echo "[pull] $REMOTE:$REMOTE_ROOT/checkpoints/$NAME -> $LOCAL_DIR"
rsync -avz --partial --progress \
  --exclude 'optimizer.pt' \
  --exclude 'scheduler.pt' \
  --exclude 'training_args.bin' \
  --exclude 'global_step*/' \
  --exclude 'rng_state*.pth' \
  "$REMOTE:$REMOTE_ROOT/checkpoints/$NAME/" "$LOCAL_DIR/"
echo "[pull] OK — adapter at $LOCAL_DIR"
ls -lh "$LOCAL_DIR" | head -10
