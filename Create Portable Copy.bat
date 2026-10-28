@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
set "WORKSPACE_PYTHON=%CD%\runtime\python\python.exe"
if not exist "%WORKSPACE_PYTHON%" set "WORKSPACE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%WORKSPACE_PYTHON%" (
    echo Run Setup_Combined.bat first.
    popd
    pause
    exit /b 1
)
"%WORKSPACE_PYTHON%" make_portable.py
set "WORKSPACE_RESULT=%ERRORLEVEL%"
popd
pause
exit /b %WORKSPACE_RESULT%
