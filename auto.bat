@echo off
rem Run by Windows Task Scheduler (see install_auto.bat). No prompts; log goes to logs\auto.log
cd /d "%~dp0"
if not exist logs mkdir logs
set AUTO=1
call collect.bat vworld seoul+seongnam >> logs\auto.log 2>&1
