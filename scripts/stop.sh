#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"
PID_FILE="$($PYTHON_EXE -c 'from app.app_paths import get_runtime_pid_file; print(get_runtime_pid_file())' 2>/dev/null)"
LOCK_FILE="$($PYTHON_EXE -c 'from app.app_paths import get_runtime_lock_file; print(get_runtime_lock_file())' 2>/dev/null)"

if [[ -z "$PID_FILE" || -z "$LOCK_FILE" ]]; then
  echo "Failed to resolve runtime paths."
  exit 1
fi

if [[ ! -f "$PID_FILE" ]]; then
  echo "assistant-runtime is not running (no PID file found)."
  rm -f "$LOCK_FILE"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped assistant-runtime (PID $PID)."
else
  echo "assistant-runtime PID file was stale."
fi

rm -f "$PID_FILE" "$LOCK_FILE"
