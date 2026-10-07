@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Installs or repairs the tool: .venv, packages, models, desktop shortcut. Safe to run again.
rem Arguments go to tools\install.ps1, e.g.  install.bat -Torch cpu
rem a PowerShell 7 window's module path breaks Windows PowerShell: let it use its own
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1" %*
set code=%errorlevel%
echo.
pause
exit /b %code%
