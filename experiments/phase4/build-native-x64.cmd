@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase4\build-tsf.cmd"
if errorlevel 1 exit /b %errorlevel%
call "experiments\phase4\build-service-x64.cmd"
exit /b %errorlevel%
