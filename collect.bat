@echo off
rem Redev-map: collect VWorld data on this PC (Korean IP) and push to GitHub.
rem   collect.bat                -> Seoul + Seongnam
rem   collect.bat vworld test    -> Seocho-gu only
rem   collect.bat check test     -> test the APIs only (same as check.bat)
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
set MODE=%~1
if "%MODE%"=="" set MODE=vworld
set REGION=%~2
if "%REGION%"=="" set REGION=seoul+seongnam

if not exist .env (
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

.venv\Scripts\python.exe -m pipeline.fetch %REGION% %MODE%
set RC=%errorlevel%

if /i "%MODE%"=="vworld" (
  git add data/seed
  git diff --cached --quiet && echo No new data to upload.
  git diff --cached --quiet || (git commit -q -m "VWorld data update: %REGION%" && git push -q && echo Uploaded. GitHub will rebuild the map in a few minutes.)
)
if not "%RC%"=="0" echo [!] Some items failed. Run again to retry only the failed ones.

:end
pause
