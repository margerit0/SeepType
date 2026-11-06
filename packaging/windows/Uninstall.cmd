@echo off
powershell.exe -NoLogo -NoProfile -File "%~dp0Uninstall.ps1" %*
exit /b %errorlevel%
