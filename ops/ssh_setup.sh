#!/usr/bin/env bash
# ops/ssh_setup.sh — Phase H3 sanity check.
#
# Smoke-tests SSH connectivity to the remote training host and confirms
# the host key is recorded in ~/.ssh/known_hosts. Does NOT modify ssh
# config or copy keys; that is a one-time operator step.
#
# Expected ~/.ssh/config entry (already in place on this machine):
#   Host ivlab
#     HostName 10.35.13.38
#     User lrrelevant
#     IdentityFile ~/.ssh/id_ed25519
#
# Usage:
#   bash ops/ssh_setup.sh             # alias 'ivlab'
#   REMOTE=remote-gpu bash ops/ssh_setup.sh
set -uo pipefail
REMOTE="${REMOTE:-ivlab}"

echo "Probing SSH to '$REMOTE' (BatchMode, no password fallback) ..."
if ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" 'echo OK_SSH && hostname && uname -srm' 2>&1; then
  echo "OK"
  exit 0
else
  rc=$?
  cat >&2 <<'EOF'
SSH failed in BatchMode. Likely causes:
  1. The local ~/.ssh/config has no 'Host' entry for the alias.
  2. ssh-agent does not hold the right private key.
  3. The remote network is unreachable from this machine.
  4. The public key has not been installed on the remote
     (run ssh-copy-id once from a session where password auth is allowed).
EOF
  exit "$rc"
fi
