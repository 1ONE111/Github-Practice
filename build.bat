@echo off
rem ------------------------------------------------------------
rem  Build dist\NaverCrawler.exe  (double-click this file)
rem  Needs Python 3.10+ from https://www.python.org (check "Add to PATH")
rem ------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    %PY% -m venv .venv || goto :fail
)

echo [2/3] Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt || goto :fail

echo [3/3] Building exe...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean NaverCrawler.spec || goto :fail
".venv\Scripts\python.exe" -c "import subprocess,sys; sys.exit(subprocess.call([r'dist\NaverCrawler.exe','--selftest']))" || goto :fail

echo.
echo Done:  %cd%\dist\NaverCrawler.exe
explorer dist
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up to see the error.
pause
exit /b 1
