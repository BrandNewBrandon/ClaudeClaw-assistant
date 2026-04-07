@echo off
:: Windows Install.bat — double-click this file in File Explorer to install assistant-runtime.
:: Opens PowerShell and runs the installer. No extra configuration required.
::
:: Note: -ExecutionPolicy Bypass applies only to this single run.
:: It does not change your system-wide PowerShell policy.

cd /d "%~dp0"
PowerShell.exe -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
