@echo off
rem Global "alarm" command - launches the air-raid alert monitor.
rem %~dp0 is the folder this .cmd lives in (resolved at runtime), so the
rem command keeps working even if this folder is moved or renamed.
python "%~dp0alert_watcher.py" %*
