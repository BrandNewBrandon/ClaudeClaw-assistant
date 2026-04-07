$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = 'python'

Set-Location $projectRoot

$pidFile = python -c "from app.app_paths import ensure_runtime_dirs, get_runtime_pid_file; ensure_runtime_dirs(); print(get_runtime_pid_file())"
$logFile = python -c "from app.app_paths import ensure_runtime_dirs, get_logs_file; ensure_runtime_dirs(); print(get_logs_file())"

if (-not $pidFile -or -not $logFile) {
    throw 'Failed to resolve runtime paths.'
}

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid) {
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProcess) {
            Write-Host "assistant-runtime appears to already be running (PID $existingPid)."
            exit 0
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Write-Host 'Starting assistant-runtime...'
$process = Start-Process -FilePath $pythonExe -ArgumentList '-m', 'app.main' -WorkingDirectory $projectRoot -RedirectStandardOutput $logFile -RedirectStandardError $logFile -PassThru
Set-Content -Path $pidFile -Value $process.Id
Write-Host "Started assistant-runtime (PID $($process.Id))."
