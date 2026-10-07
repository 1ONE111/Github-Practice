@echo off
rem Run from source without building an exe (installs packages on first run)
setlocal
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv || goto :fail
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)
start "" ".venv\Scripts\pythonw.exe" -m naver_crawler
exit /b 0
:fail
echo Setup failed.
pause
exit /b 1
