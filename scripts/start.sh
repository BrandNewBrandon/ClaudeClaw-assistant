#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_EXE="${PYTHON_EXE:-python3}"
PID_FILE="$($PYTHON_EXE -c 'from app.app_paths import ensure_runtime_dirs, get_runtime_pid_file; ensure_runtime_dirs(); print(get_runtime_pid_file())' 2>/dev/null)"
LOG_FILE="$($PYTHON_EXE -c 'from app.app_paths import ensure_runtime_dirs, get_logs_file; ensure_runtime_dirs(); print(get_logs_file())' 2>/dev/null)"

if [[ -z "$PID_FILE" || -z "$LOG_FILE" ]]; then
  echo "Failed to resolve runtime paths."
  exit 1
fi

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE")"
  if kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "assistant-runtime appears to already be running (PID $EXISTING_PID)."
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

cd "$PROJECT_ROOT"
nohup "$PYTHON_EXE" -m app.main >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
echo "Started assistant-runtime (PID $NEW_PID)."
