$ErrorActionPreference = 'SilentlyContinue'

$pidFile = python -c "from app.app_paths import get_runtime_pid_file; print(get_runtime_pid_file())"

if (-not $pidFile) {
    Write-Host 'Failed to resolve runtime paths.'
    exit 1
}

if (-not (Test-Path $pidFile)) {
    Write-Host 'assistant-runtime is not running.'
    exit 0
}

$pid = (Get-Content $pidFile -Raw).Trim()
$process = if ($pid) { Get-Process -Id $pid -ErrorAction SilentlyContinue } else { $null }

if (-not $process) {
    Write-Host 'assistant-runtime is not running, but PID file exists (stale).'
    exit 1
}

Write-Host "assistant-runtime is running (PID $pid)."
