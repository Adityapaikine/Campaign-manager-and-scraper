@echo off
setlocal EnableExtensions DisableDelayedExpansion
if "%~1"=="" (
    start "" "%SystemRoot%\System32\wscript.exe" //nologo "%~dp0Start Lead Workspace.vbs"
    exit /b 0
)
pushd "%~dp0"
set "WORKSPACE_PYTHON=%CD%\runtime\python\python.exe"
if not exist "%WORKSPACE_PYTHON%" set "WORKSPACE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%WORKSPACE_PYTHON%" (
    echo Run Setup_Combined.bat first.
    popd
    exit /b 1
)
if /i "%~1"=="--check" (
    "%WORKSPACE_PYTHON%" run.py --check
) else (
    "%WORKSPACE_PYTHON%" run.py
)
set "WORKSPACE_RESULT=%ERRORLEVEL%"
popd
exit /b %WORKSPACE_RESULT%
