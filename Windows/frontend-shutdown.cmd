:: frontend-shutdown.bat (Windows)
@echo off
REM Shuts down the TDC001 frontend (GUI) container. Calls the PowerShell script and keeps the window open.
powershell -NoProfile -ExecutionPolicy Bypass -NoExit ^
    -File "%~dp0frontend-shutdown.ps1"
echo.
echo Press any key to close this window ...
pause > nul

