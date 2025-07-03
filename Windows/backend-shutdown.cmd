:: backend-shutdown.bat (Windows)
@echo off
REM Shuts down the TDC001 backend container. This script will call the PowerShell script and keep the window open.
powershell -NoProfile -ExecutionPolicy Bypass -NoExit ^
    -File "%~dp0backend-shutdown.ps1"
echo.
echo Press any key to close this window ...
pause > nul

