@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute scripts\install.ps1 primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m vocal_app
if errorlevel 1 pause
