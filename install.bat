@echo off
rem Double-click launcher for the PowerShell installer.
rem -ExecutionPolicy Bypass avoids the "scripts are disabled" error.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
