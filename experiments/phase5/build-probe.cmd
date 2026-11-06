@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
call "%STUDY_VS_ROOT%\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
if not exist "experiments\phase5\build" mkdir "experiments\phase5\build"
cl /nologo /std:c++17 /EHsc /O2 /MT /utf-8 /W4 /I ".cache\rime-1.13.1\dist\include" "experiments\phase3\engine_probe.cpp" /Fo"experiments\phase5\build\engine_probe_x64.obj" /Fe"experiments\phase5\build\engine_probe_x64.exe" /link /MANIFEST:EMBED /MANIFESTUAC:"level='asInvoker' uiAccess='false'"
exit /b %errorlevel%
