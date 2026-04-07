$ErrorActionPreference = 'SilentlyContinue'

$pidFile = python -c "from app.app_paths import get_runtime_pid_file; print(get_runtime_pid_file())"
$lockFile = python -c "from app.app_paths import get_runtime_lock_file; print(get_runtime_lock_file())"

if (-not $pidFile -or -not $lockFile) {
    Write-Host 'Failed to resolve runtime paths.'
    exit 1
}

if (-not (Test-Path $pidFile)) {
    Write-Host 'assistant-runtime is not running (no PID file found).'
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    exit 0
}

$pid = (Get-Content $pidFile -Raw).Trim()
if ($pid) {
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $pid -Force
        Write-Host "Stopped assistant-runtime (PID $pid)."
    } else {
        Write-Host 'assistant-runtime PID file was stale.'
    }
}

Remove-Item $pidFile, $lockFile -Force -ErrorAction SilentlyContinue
