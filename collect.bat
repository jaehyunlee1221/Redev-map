@echo off
rem Redev-map: collect VWorld data on this PC (Korean IP) and push to GitHub.
rem   collect.bat                -> Seoul + Seongnam (each district is uploaded as soon as it finishes)
rem   collect.bat vworld test    -> Seocho-gu only
rem   collect.bat check test     -> test the APIs only (same as check.bat)
rem Data downloaded recently is skipped, so running this often is cheap.
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set MODE=%~1
if "%MODE%"=="" set MODE=vworld
set REGION=%~2
if "%REGION%"=="" set REGION=seoul+seongnam
echo ===== %DATE% %TIME%  %MODE% %REGION% =====

if not exist .env (
  if defined AUTO goto :end
  echo VWORLD_KEY=paste_your_key_here> .env
  echo.
  echo [!] Paste your VWorld API key into the Notepad window, save, close it, then run this again.
  notepad .env
  goto :end
)

git config user.name >nul 2>&1 || git config user.name "redev-pc"
git config user.email >nul 2>&1 || git config user.email "redev-pc@users.noreply.github.com"
git pull --rebase --autostash -q

if not exist .venv\Scripts\python.exe (
  echo Setting up Python packages for the first time...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :end

set PUSH=1
.venv\Scripts\python.exe -m pipeline.fetch %REGION% %MODE%
if errorlevel 1 echo [!] Some items failed. They will be retried next run.
if /i "%MODE%"=="vworld" echo Done. Updated districts were uploaded; the map rebuilds on GitHub in a few minutes.

:end
if not defined AUTO pause
