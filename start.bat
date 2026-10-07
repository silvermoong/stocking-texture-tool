@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo The tool is not installed here yet: run install.bat first.
  pause
  exit /b 1
)
rem Drop a picture or PSD on this file to open it directly.
start "" ".venv\Scripts\pythonw.exe" -m stocking %*
