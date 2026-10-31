@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
if not exist "experiments\phase4\build" mkdir "experiments\phase4\build"
cl /nologo /std:c++17 /EHsc /O2 /MT /utf-8 /DUNICODE /D_UNICODE /I ".cache\rime-1.13.1\dist\include" /I "experiments\phase3" "experiments\phase4\session_actions_test.cpp" "experiments\phase3\StudyEngine.cpp" "src\study\SessionActions.cpp" /Fo"experiments\phase4\build\\" /Fe"experiments\phase4\build\session_actions_test.exe" /link /INCREMENTAL:NO
exit /b %errorlevel%
