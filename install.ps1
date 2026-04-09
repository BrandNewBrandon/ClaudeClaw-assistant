# install.ps1 - one-command installer for ClaudeClaw-assistant (Windows)
#
# Usage (from PowerShell in the project folder):
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#   .\install.ps1
#
# What it does:
#   1. Checks Python 3.11+
#   2. Creates .venv if it doesn't exist
#   3. Installs the package in editable mode
#   4. Adds .venv\Scripts to the user PATH (permanent, one time)
#   5. Runs 'assistant init' to complete setup
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot '.venv'
$VenvScripts = Join-Path $Venv 'Scripts'
$PythonMinMinor = 11

# -- Helpers ------------------------------------------------------------------
function Write-Ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  [X]  $msg" -ForegroundColor Red }
function Write-Step { param($msg) Write-Host "`n$msg" -ForegroundColor Cyan }

$banner = @'

  ╔═════════════════════════════════════════════════════════════╗

     _____ _                 _       _____ _
    / ____| |               | |     / ____| |
   | |    | | __ _ _   _  __| | ___| |    | | __ ___      __
   | |    | |/ _` | | | |/ _` |/ _ \ |    | |/ _` \ \ /\ / /
   | |____| | (_| | |_| | (_| |  __/ |____| | (_| |\ V  V /
    \_____|_|\__,_|\__,_|\__,_|\___|\_____|_|\__,_| \_/\_/

  ╠═════════════════════════════════════════════════════════════╣
           Your AI assistant, locally hosted.
  ╚═════════════════════════════════════════════════════════════╝

'@
Write-Host $banner -ForegroundColor Cyan

# -- Guard: auto-relocate if run from a system directory ----------------------
$systemRoots = @($env:SystemRoot, $env:ProgramFiles, ${env:ProgramFiles(x86)})
foreach ($sysRoot in $systemRoots) {
    if ($sysRoot -and $ProjectRoot.StartsWith($sysRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        $SafeRoot = "C:\Users\$env:USERNAME\ClaudeClaw\assistant"
        Write-Host ""
        Write-Host "  [!]  Installer is running from a system directory:" -ForegroundColor Yellow
        Write-Host "       $ProjectRoot" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Copying project to: $SafeRoot" -ForegroundColor Cyan
        New-Item -ItemType Directory -Force -Path $SafeRoot | Out-Null
        robocopy $ProjectRoot $SafeRoot /E /NFL /NDL /NJH /NJS | Out-Null
        Write-Host "  [OK] Copied." -ForegroundColor Green
        Write-Host ""
        Write-Host "  The original copy can be deleted once setup is complete." -ForegroundColor Yellow
        Write-Host "  To remove it, run in an admin PowerShell:" -ForegroundColor Yellow
        Write-Host "    Remove-Item -Recurse -Force `"$ProjectRoot`"" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Relaunching installer from the new location..." -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$SafeRoot\install.ps1`"" -Wait
        exit 0
    }
}

# -- Helper: find a suitable Python -------------------------------------------
function Find-Python {
    $Candidates = @('python3.13', 'python3.12', 'python3.11', 'python3', 'python')
    foreach ($candidate in $Candidates) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) {
            try {
                $major = & $candidate -c 'import sys; print(sys.version_info.major)' 2>$null
                $minor = & $candidate -c 'import sys; print(sys.version_info.minor)' 2>$null
                if ([int]$major -eq 3 -and [int]$minor -ge $PythonMinMinor) {
                    return $candidate
                }
            } catch {}
        }
    }
    return $null
}

# -- Step 1: Find Python ------------------------------------------------------
Write-Step "Step 1 - Checking Python"

$PythonExe = Find-Python

if ($PythonExe) {
    $PythonVersion = & $PythonExe --version 2>&1
    Write-Ok "Found $PythonVersion ($PythonExe)"
} else {
    Write-Warn "Python 3.$PythonMinMinor+ not found."
    Write-Host ""
    $answer = Read-Host "  Would you like to install it now? [Y/n]"
    if (-not $answer) { $answer = 'Y' }

    if ($answer -match '^[Yy]') {
        $wingetFound = Get-Command winget -ErrorAction SilentlyContinue
        if ($wingetFound) {
            Write-Host "  Installing Python 3.12 via winget..."
            winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
            # Refresh PATH so we can find the new Python
            $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH', 'User')
        } else {
            Write-Warn "winget not available. Trying python.org installer..."
            Write-Host "  Downloading Python 3.12 installer..."
            $installerUrl = 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe'
            $installerPath = Join-Path $env:TEMP 'python-installer.exe'
            Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
            Write-Host "  Running Python installer (this may take a minute)..."
            Start-Process -Wait -FilePath $installerPath -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1'
            Remove-Item $installerPath -ErrorAction SilentlyContinue
            # Refresh PATH
            $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH', 'User')
        }

        # Re-check after install
        $PythonExe = Find-Python
        if ($PythonExe) {
            $PythonVersion = & $PythonExe --version 2>&1
            Write-Ok "Installed $PythonVersion ($PythonExe)"
        } else {
            Write-Fail "Python install did not succeed."
            Write-Host ""
            Write-Host "  Download manually from: https://www.python.org/downloads/"
            Write-Host "  Make sure to check 'Add Python to PATH' during install."
            Write-Host "  Then re-run this installer."
            Write-Host ""
            exit 1
        }
    } else {
        Write-Host ""
        Write-Host "  Download from: https://www.python.org/downloads/"
        Write-Host "  Make sure to check 'Add Python to PATH' during install."
        Write-Host "  Then re-run this installer."
        Write-Host ""
        exit 1
    }
}

# -- Step 2: Check claude CLI -------------------------------------------------
Write-Step "Step 2 - Checking prerequisites"

$claudeFound = Get-Command claude -ErrorAction SilentlyContinue
if ($claudeFound) {
    Write-Ok "claude CLI found"
} else {
    Write-Warn "claude CLI not found in PATH"
    Write-Host ""
    $answer = Read-Host "  Would you like to install it now? [Y/n]"
    if (-not $answer) { $answer = 'Y' }

    if ($answer -match '^[Yy]') {
        $npmFound = Get-Command npm -ErrorAction SilentlyContinue
        if ($npmFound) {
            Write-Host "  Installing Claude Code via npm..."
            npm install -g @anthropic-ai/claude-code
        } else {
            Write-Warn "npm not found. Cannot auto-install Claude CLI."
        }

        $claudeFound = Get-Command claude -ErrorAction SilentlyContinue
        if ($claudeFound) {
            Write-Ok "claude CLI installed"
        } else {
            Write-Warn "Claude CLI install did not succeed."
            Write-Host "       Install it manually from: https://claude.ai/code"
            Write-Host "       You can install it after setup and before running 'assistant start'."
        }
    } else {
        Write-Warn "Skipping Claude CLI install."
        Write-Host "       Install it from: https://claude.ai/code"
        Write-Host "       You can install it after setup and before running 'assistant start'."
    }
}

# -- Step 3: Create venv ------------------------------------------------------
Write-Step "Step 3 - Setting up virtual environment"

$VenvPython = Join-Path $VenvScripts 'python.exe'
if ((Test-Path $Venv) -and (Test-Path $VenvPython)) {
    Write-Ok "Virtual environment already exists at $Venv"
} else {
    Write-Host "  Creating .venv..."
    & $PythonExe -m venv $Venv
    Write-Ok "Created .venv"
}

# -- Step 4: Install package --------------------------------------------------
Write-Step "Step 4 - Installing ClaudeClaw"

& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -e $ProjectRoot
Write-Ok "Installed ClaudeClaw (editable mode)"

# -- Step 5: Add to PATH ------------------------------------------------------
Write-Step "Step 5 - Adding 'assistant' to PATH"

$currentUserPath = [System.Environment]::GetEnvironmentVariable('PATH', 'User')
if ($currentUserPath -like "*$VenvScripts*") {
    Write-Ok "PATH already contains $VenvScripts - skipping"
} else {
    $newPath = "$VenvScripts;$currentUserPath"
    [System.Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
    Write-Ok "Added $VenvScripts to your user PATH (permanent)"
    Write-Host "  This takes effect in new terminal windows."
}

# Also add to current session so assistant init works immediately
$env:PATH = "$VenvScripts;$env:PATH"

# -- Step 6: Verify -----------------------------------------------------------
Write-Step "Step 6 - Verifying install"

$AssistantExe = Join-Path $VenvScripts 'assistant.exe'
if (Get-Command assistant -ErrorAction SilentlyContinue) {
    $assistantPath = (Get-Command assistant).Source
    Write-Ok "assistant command available at $assistantPath"
    $AssistantCmd = 'assistant'
} elseif (Test-Path $AssistantExe) {
    Write-Ok "assistant found at $AssistantExe"
    $AssistantCmd = $AssistantExe
} else {
    Write-Warn "Could not find 'assistant' in PATH for this session - using full path."
    $AssistantCmd = $AssistantExe
}

# -- Step 7: Run init ---------------------------------------------------------
Write-Step "Step 7 - First-time setup"
Write-Host ""
Write-Host "  Installation complete! Launching setup wizard..."
Write-Host ""
Start-Sleep -Milliseconds 500

& $AssistantCmd init

# -- Done ---------------------------------------------------------------------
Write-Host ""
Write-Host "  Installation complete." -ForegroundColor Green
Write-Host ""
Write-Host "  The 'assistant' command is now available in new terminal windows."
Write-Host "  Open a new PowerShell window and run:  assistant start"
Write-Host ""
