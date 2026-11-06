@echo off
powershell.exe -NoLogo -NoProfile -File "%~dp0Install.ps1" %*
exit /b %errorlevel%
