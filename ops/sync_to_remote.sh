#!/usr/bin/env bash
# ops/sync_to_remote.sh — clone or fast-forward the repo on the remote.
#
# Default remote root is /data2/lrrelevant/ve401-solver because the
# remote's $HOME (/dev/sda4) was 98% full as of 2026-04-28; /data2
# (15 TB, 9.4 TB free) is the safe place for code + checkpoints.
#
# On first run: clones git@github.com:Guilty-C/ECE4010J-Final-Exam.git
# On later runs: git fetch + git pull --ff-only on main.
#
# Usage:
#   bash ops/sync_to_remote.sh
#   REMOTE=remote-gpu REMOTE_ROOT=/data/foo bash ops/sync_to_remote.sh
set -euo pipefail
REMOTE="${REMOTE:-ivlab}"
REMOTE_ROOT="${REMOTE_ROOT:-/data2/lrrelevant/ve401-solver}"
REMOTE_GIT_URL="${REMOTE_GIT_URL:-git@github.com:Guilty-C/ECE4010J-Final-Exam.git}"
BRANCH="${BRANCH:-main}"

ssh -o BatchMode=yes "$REMOTE" "REMOTE_ROOT='$REMOTE_ROOT' REMOTE_GIT_URL='$REMOTE_GIT_URL' BRANCH='$BRANCH' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
mkdir -p "$(dirname "$REMOTE_ROOT")"
if [ -d "$REMOTE_ROOT/.git" ]; then
  echo "[sync] existing clone at $REMOTE_ROOT — git fetch + ff pull"
  cd "$REMOTE_ROOT"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  echo "[sync] cloning $REMOTE_GIT_URL into $REMOTE_ROOT"
  git clone --branch "$BRANCH" "$REMOTE_GIT_URL" "$REMOTE_ROOT"
  cd "$REMOTE_ROOT"
fi
echo "[sync] HEAD: $(git rev-parse --short HEAD) ($(git log -1 --pretty=%s))"
REMOTE_SCRIPT
