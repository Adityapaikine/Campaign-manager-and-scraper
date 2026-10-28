@echo off
cd /d "%~dp0"
set "TEAM_PYTHON=%~dp0runtime\python\python.exe"
if not exist "%TEAM_PYTHON%" set "TEAM_PYTHON=%~dp0.venv\Scripts\python.exe"
"%TEAM_PYTHON%" "%~dp0team_server.py" setup
pause
