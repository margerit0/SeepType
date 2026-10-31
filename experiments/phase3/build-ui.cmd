@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
if not exist "experiments\phase3\build\ui" mkdir "experiments\phase3\build\ui"
set "STUDY_UI_OPT=/O2"
if /i "%~1"=="debug" set "STUDY_UI_OPT=/Od"
cl /nologo /std:c++17 /EHsc %STUDY_UI_OPT% /Oy- /MT /utf-8 /DUNICODE /D_UNICODE /DWEASEL_STUDY_SPIKE /I ".cache\rime-1.13.1\dist\include" /I ".cache\src\weasel\include" /I ".cache\src\weasel\WeaselUI" /I ".cache\src\weasel\WeaselServer" /I ".cache\src\boost_1_84_0" /I "experiments\phase3" "experiments\phase3\ui_probe.cpp" "experiments\phase3\StudyEngine.cpp" "experiments\phase3\StudyLayout.cpp" ".cache\src\weasel\WeaselUI\*.cpp" /Fo"experiments\phase3\build\ui\\" /Fe"experiments\phase3\build\ui_probe.exe" /link /INCREMENTAL:NO /MAP:"experiments\phase3\build\ui_probe.map" /SUBSYSTEM:WINDOWS /ENTRY:wmainCRTStartup user32.lib gdi32.lib comctl32.lib ole32.lib advapi32.lib shell32.lib
exit /b %errorlevel%
