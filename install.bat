@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Installs, repairs or updates the tool: the newest code from GitHub, then .venv, packages, models, desktop shortcut.
rem Safe to run again. Arguments go to tools\install.ps1, e.g.  install.bat -Torch cpu   or   install.bat -NoUpdate
rem a PowerShell 7 window's module path breaks Windows PowerShell: let it use its own
set "PSModulePath="
rem The update can rewrite this file while it runs, and cmd reads a batch file line by line as it goes: everything
rem after this point is one block, read whole before it starts (call makes %%...%% expand when each line runs).
(
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1" %*
  call set code=%%errorlevel%%
  echo.
  pause
  call exit /b %%code%%
)
