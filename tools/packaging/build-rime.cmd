@echo off
setlocal
chcp 65001 >nul
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
call "%STUDY_VS_ROOT%\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
python tools\packaging\build_rime.py
exit /b %errorlevel%
