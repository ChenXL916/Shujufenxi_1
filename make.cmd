@echo off
set "PROJECT_PYTHON=%~dp0apps\api\.venv\Scripts\python.exe"
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
set "PYTHONPATH=%~dp0apps\api"
set "VIRTUAL_ENV=%~dp0apps\api\.venv"
"%PROJECT_PYTHON%" "%~dp0scripts\task_runner.py" %*
