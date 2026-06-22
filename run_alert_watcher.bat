@echo off
rem Launches alert_watcher.py as a NEW TAB in the current Windows Terminal window.
rem Uses %~dp0 (this file's folder), so it survives moving/renaming.
setlocal

rem Strip trailing "\" so the closing quote is not escaped by it.
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
if exist "%WT%" (
    rem -w 0  -> use the CURRENT Windows Terminal window (new tab in it).
    "%WT%" -w 0 new-tab --title "Alert Watcher - Kyiv" -d "%HERE%" cmd /k python alert_watcher.py
) else (
    rem Fallback: no Windows Terminal -> open a classic window.
    start "Alert Watcher - Kyiv" cmd /k "cd /d ""%HERE%"" && python alert_watcher.py"
)

endlocal
