@echo off
rem Background/autostart launcher: starts minimized, pops up only on alert.
rem ALERT_AUTOHIDE=1 tells the script to keep itself minimized and only
rem restore the window when an alert begins.
setlocal
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "ALERT_AUTOHIDE=1"
start "Alert Watcher - Kyiv" /min /d "%HERE%" cmd /k "python alert_watcher.py"
endlocal
