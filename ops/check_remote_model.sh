#!/usr/bin/env bash
# ops/check_remote_model.sh — Phase H5 probe.
#
# Runs over SSH against the remote training host (default alias: ivlab,
# which resolves to lrrelevant@10.35.13.38 via ~/.ssh/config) and reports:
#   - hostname, kernel, CPU/RAM/disk capacity
#   - GPU inventory (nvidia-smi)
#   - HuggingFace cache layout (Qwen2.5-3B-Instruct candidate paths from
#     plan §8.2)
#   - which conda envs already carry torch / transformers / peft / accelerate
#
# Output is plain text suitable for pasting into progress.md.
#
# Usage:
#   bash ops/check_remote_model.sh                 # default alias 'ivlab'
#   REMOTE=remote-gpu bash ops/check_remote_model.sh
#
# Exit codes:
#   0  probe completed (model presence is reported, not asserted)
#   1  SSH connection failed
set -uo pipefail

REMOTE="${REMOTE:-ivlab}"
echo "=== ve401-solver Phase H5 probe ==="
echo "remote alias : $REMOTE"
echo "local time   : $(date -Iseconds 2>/dev/null || date)"
echo

if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" 'echo OK' >/dev/null 2>&1; then
  echo "FAIL: SSH to '$REMOTE' refused or timed out." >&2
  echo "      Verify ~/.ssh/config has a Host entry and key auth works." >&2
  exit 1
fi

ssh -o BatchMode=yes "$REMOTE" 'bash -s' <<'REMOTE_SCRIPT'
set -u

echo "--- system ---"
echo "hostname : $(hostname)"
echo "kernel   : $(uname -srm)"
echo "uptime   : $(uptime | sed "s/^ *//")"
echo

echo "--- gpu (nvidia-smi) ---"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,memory.used,driver_version \
             --format=csv,noheader 2>&1 | sed "s/^/  /"
else
  echo "  (nvidia-smi not on PATH)"
fi
echo

echo "--- memory (free -h) ---"
free -h | sed "s/^/  /"
echo

echo "--- disk (df -h, top mounts) ---"
df -h --output=source,size,used,avail,pcent,target 2>/dev/null \
  | grep -E "^(/dev/|Filesystem|Source)" \
  | grep -v "/snap/" \
  | sed "s/^/  /"
echo

echo "--- Qwen2.5-3B-Instruct candidate paths (plan §8.2) ---"
for p in \
    "$HOME/.cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct" \
    "$HOME/models/Qwen2.5-3B-Instruct" \
    "$HOME/Qwen2.5-3B-Instruct" \
    "/data/models/Qwen2.5-3B-Instruct" \
    "/opt/models/Qwen2.5-3B-Instruct" \
    "/workspace/models/Qwen2.5-3B-Instruct" \
    "/home/lrrelevant/models/Qwen2.5-3B-Instruct"
do
  if [ -e "$p" ]; then
    sz=$(du -sh "$p" 2>/dev/null | awk "{print \$1}")
    echo "  FOUND $p   ($sz)"
  else
    echo "  miss  $p"
  fi
done
echo

echo "--- HF cache root (resolved via symlink if any) ---"
hf_hub="$HOME/.cache/huggingface/hub"
if [ -L "$hf_hub" ]; then
  echo "  $hf_hub -> $(readlink -f "$hf_hub")"
elif [ -d "$hf_hub" ]; then
  echo "  $hf_hub (directory)"
else
  echo "  (no HF cache directory)"
fi
ls -d "$hf_hub"/models--*Qwen* 2>/dev/null | sed "s/^/    /" || true
echo

echo "--- conda envs with usable torch+transformers+peft+accelerate ---"
conda_bin="$HOME/miniconda3/bin/conda"
if [ -x "$conda_bin" ]; then
  envs=$("$conda_bin" info --envs 2>/dev/null | awk '/^[^#]/ {print $NF}' | grep -v "^$")
  for envpath in $envs; do
    py="$envpath/bin/python"
    [ -x "$py" ] || continue
    label="$(basename "$envpath")"
    out=$("$py" - <<PY 2>/dev/null
try:
    import torch, transformers, peft, accelerate
    print(f"OK torch={torch.__version__} cuda={torch.cuda.is_available()} transformers={transformers.__version__} peft={peft.__version__} accelerate={accelerate.__version__}")
except Exception as e:
    print(f"MISS {type(e).__name__}: {e}")
PY
)
    printf "  %-45s %s\n" "$label" "$out"
  done
else
  echo "  (no miniconda3 at $conda_bin)"
fi
echo

echo "--- repo presence ---"
for r in \
    "$HOME/ECE4010J-Final-Exam" \
    "$HOME/ve401-solver" \
    "$HOME/ve401_solver" \
    "/data2/lrrelevant/ve401-solver" \
    "/data2/lrrelevant/ECE4010J-Final-Exam"
do
  if [ -d "$r/.git" ]; then
    head=$(git -C "$r" rev-parse --short HEAD 2>/dev/null || echo "?")
    echo "  CLONE $r   (HEAD=$head)"
  elif [ -d "$r" ]; then
    echo "  EXISTS_NOT_GIT $r"
  else
    echo "  miss  $r"
  fi
done

REMOTE_SCRIPT
