@echo off
REM Launch from the prepared Python environment without dependency resolution.
cd /d "%~dp0\..\.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\install.ps1 -Mode Offline after provisioning the pilot.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\pilot_setup.py launch
exit /b %errorlevel%
