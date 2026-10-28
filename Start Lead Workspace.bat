@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
set "WORKSPACE_PYTHON=%CD%\runtime\python\pythonw.exe"
if not exist "%WORKSPACE_PYTHON%" set "WORKSPACE_PYTHON=%CD%\.venv\Scripts\pythonw.exe"
if not exist "%WORKSPACE_PYTHON%" (
    echo Copy the entire portable folder, including runtime, then try again.
    echo For a source-only copy, run Setup_Combined.bat first.
    popd
    pause
    exit /b 1
)
start "" "%WORKSPACE_PYTHON%" "%CD%\run.pyw"
popd
exit /b 0
