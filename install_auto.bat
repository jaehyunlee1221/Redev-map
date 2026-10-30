@echo off
rem Register (or with "remove", unregister) the daily auto-run task. No admin rights needed.
cd /d "%~dp0"
if /i "%~1"=="remove" (
  powershell -NoProfile -ExecutionPolicy Bypass -File setup\install_auto.ps1 -Remove
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File setup\install_auto.ps1
)
pause
