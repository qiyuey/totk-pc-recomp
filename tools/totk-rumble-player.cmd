@echo off
setlocal
set "project=%~dp0.."
if not exist "%project%\.venv\Scripts\pythonw.exe" (
    echo Python environment not found: "%project%\.venv"
    pause
    exit /b 1
)
start "" "%project%\.venv\Scripts\pythonw.exe" "%~dp0totk_rumble_player.py"
