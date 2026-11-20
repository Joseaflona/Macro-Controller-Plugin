@echo off
cd /d "%~dp0"
py -m padmidi %*
if errorlevel 1 pause
