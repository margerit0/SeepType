@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
call "%STUDY_VS_ROOT%\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
python experiments\phase4\build-service.py --tsf --product
if errorlevel 1 exit /b %errorlevel%
python experiments\phase4\build-service.py --service-x64 --product
if errorlevel 1 exit /b %errorlevel%
set "VSLANG=1033"
python tools\packaging\record_build.py
exit /b %errorlevel%
