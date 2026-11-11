@echo off
setlocal
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe -X utf8 "%~dp0tools\android\acceptance.py" %*
    exit /b 0
)
where python.exe >nul 2>nul
if errorlevel 1 (
    echo Python 3.11+ with tkinter is required. See docs\android-acceptance.md.
    pause
    exit /b 1
)
python.exe -X utf8 "%~dp0tools\android\acceptance.py" %*
if errorlevel 1 pause
