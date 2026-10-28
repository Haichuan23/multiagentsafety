#!/usr/bin/env bash
# Detach any command and capture output. Example: scripts/detached.sh check scripts/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?Usage: detached.sh SESSION COMMAND [ARG ...]}"
shift
[[ "$name" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid session name' >&2; exit 2; }
[[ $# -gt 0 ]] || { echo 'Missing command' >&2; exit 2; }
mkdir -p logs
if tmux -L networkproject has-session -t "$name" 2>/dev/null; then
  echo "Session already running: $name" >&2
  exit 2
fi
rm -f "logs/$name.exit"
printf -v escaped '%q ' "$@"
printf -v workdir '%q' "$PWD"
printf -v logfile '%q' "$PWD/logs/$name.log"
printf -v statusfile '%q' "$PWD/logs/$name.exit"
# Remain attached to a server on this host even after the SSH client closes.
tmux -L networkproject new-session -d -s "$name" "cd $workdir; $escaped >$logfile 2>&1; status=\$?; echo \$status >$statusfile; exit \$status"
echo "Started on $(hostname). Log: logs/$name.log; exit code: logs/$name.exit"
echo "Attach on this host: tmux -L networkproject attach -t $name"
