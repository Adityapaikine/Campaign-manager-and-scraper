@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
set "WORKSPACE_PYTHON=%CD%\runtime\python\python.exe"
if not exist "%WORKSPACE_PYTHON%" set "WORKSPACE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%WORKSPACE_PYTHON%" (
    echo The runtime folder is missing. Copy the complete portable application.
    popd
    pause
    exit /b 1
)
"%WORKSPACE_PYTHON%" portable_check.py --browser
set "WORKSPACE_RESULT=%ERRORLEVEL%"
popd
pause
exit /b %WORKSPACE_RESULT%
