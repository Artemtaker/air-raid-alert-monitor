@echo off
rem Autostart launcher: opens the monitor as a NEW TAB in Windows Terminal.
rem If no Windows Terminal window is open yet (e.g. right after login),
rem -w 0 creates one and puts the monitor tab in it.
setlocal
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
if exist "%WT%" (
    "%WT%" -w 0 new-tab --title "Alert Watcher - Kyiv" -d "%HERE%" cmd /k python alert_watcher.py
) else (
    rem Fallback: no Windows Terminal -> classic minimized window with autohide.
    set "ALERT_AUTOHIDE=1"
    start "Alert Watcher - Kyiv" /min /d "%HERE%" cmd /k "python alert_watcher.py"
)
endlocal
