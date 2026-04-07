#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"
PID_FILE="$($PYTHON_EXE -c 'from app.app_paths import get_runtime_pid_file; print(get_runtime_pid_file())' 2>/dev/null)"

if [[ -z "$PID_FILE" ]]; then
  echo "Failed to resolve runtime paths."
  exit 1
fi

if [[ ! -f "$PID_FILE" ]]; then
  echo "assistant-runtime is not running."
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  echo "assistant-runtime is running (PID $PID)."
else
  echo "assistant-runtime is not running, but PID file exists (stale)."
  exit 1
fi
