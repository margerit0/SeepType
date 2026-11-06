@echo off
setlocal
cd /d "%~dp0..\.."
call "experiments\phase3\vs-env.cmd"
if errorlevel 1 exit /b %errorlevel%
call "%STUDY_VS_ROOT%\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
if not exist ".cache\packaging\registration-test" mkdir ".cache\packaging\registration-test"
cl /nologo /std:c++17 /EHsc /O2 /MT /utf-8 /Brepro /I src tools\packaging\registration_flow_test.cpp /Fo.cache\packaging\registration-test\flow.obj /Fe.cache\packaging\registration-test\flow.exe /link /Brepro > ".cache\packaging\registration-test\build.log" 2>&1
if errorlevel 1 (
  type ".cache\packaging\registration-test\build.log"
  exit /b 1
)
python tools\packaging\verify_registration.py
exit /b %errorlevel%
