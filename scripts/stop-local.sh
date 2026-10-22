#!/usr/bin/env bash
# stop-local.sh — Stops all locally running Campus Sentinel processes
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/.pids"

stop_pid() {
  local name=$1 file="$PID_DIR/$1.pid"
  if [[ -f "$file" ]]; then
    local pid
    pid=$(cat "$file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" && echo "✓ Stopped $name (PID $pid)"
    else
      echo "⚠  $name was not running"
    fi
    rm -f "$file"
  else
    echo "⚠  No PID file for $name"
  fi
}

stop_pid frontend
stop_pid backend
stop_pid celery

echo ""
echo "All services stopped."
echo "Postgres & Redis left running (stop with: brew services stop postgresql@15 redis)"
