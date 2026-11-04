@echo off
rem Register the weekly auto-run task (or: "install_auto.bat daily" for every day, "install_auto.bat remove" to unregister). No admin rights needed.
cd /d "%~dp0"
if /i "%~1"=="remove" (
  powershell -NoProfile -ExecutionPolicy Bypass -File setup\install_auto.ps1 -Remove
) else if /i "%~1"=="daily" (
  powershell -NoProfile -ExecutionPolicy Bypass -File setup\install_auto.ps1 -Daily
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File setup\install_auto.ps1
)
pause
