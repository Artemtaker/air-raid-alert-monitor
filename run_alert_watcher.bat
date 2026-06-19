@echo off
rem Launches alert_watcher.py in a NEW Windows Terminal window.
rem Uses %~dp0 (this file's folder), so it survives moving/renaming.
setlocal

rem Strip trailing "\" so the closing quote is not escaped by it.
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"
if exist "%WT%" (
    start "" "%WT%" -d "%HERE%" cmd /k "title Alert Watcher - Kyiv && python alert_watcher.py"
) else (
    start "Alert Watcher - Kyiv" cmd /k "cd /d ""%HERE%"" && python alert_watcher.py"
)

endlocal
