@echo off
rem Call only within a build process; never modify system/user PATH.
if not defined STUDY_VS_ROOT (
  for /f "usebackq tokens=*" %%i in (`call "%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -version "[16.0,17.0)" -property installationPath`) do set "STUDY_VS_ROOT=%%i"
)
if not exist "%STUDY_VS_ROOT%\VC\Auxiliary\Build\vcvars32.bat" (
  echo VS 2019 C++ tools not found. Set STUDY_VS_ROOT to the installed VS2019 directory.
  exit /b 1
)
call "%STUDY_VS_ROOT%\VC\Auxiliary\Build\vcvars32.bat" >nul
exit /b %errorlevel%
