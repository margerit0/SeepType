@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
if not exist "experiments\phase3\build" mkdir "experiments\phase3\build"
cl /nologo /std:c++17 /EHsc /O2 /MT /utf-8 /W4 /I ".cache\rime-1.13.1\dist\include" "experiments\phase3\engine_probe.cpp" /Fo"experiments\phase3\build\engine_probe.obj" /Fe"experiments\phase3\build\engine_probe.exe"
exit /b %errorlevel%
