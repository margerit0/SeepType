@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
python "experiments\phase4\build-service.py" %*
exit /b %errorlevel%
