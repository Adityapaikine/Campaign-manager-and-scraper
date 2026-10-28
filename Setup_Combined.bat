@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if exist "runtime\python\python.exe" (
    "runtime\python\python.exe" portable_check.py
    if errorlevel 1 goto failed
    echo This portable copy is ready. No installation is needed.
    popd
    pause
    exit /b 0
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\browsers"
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py --check
if errorlevel 1 goto failed
echo Setup complete. Open Start Lead Workspace.vbs.
popd
pause
exit /b 0
:failed
echo Setup failed. Review the message above.
popd
pause
exit /b 1
