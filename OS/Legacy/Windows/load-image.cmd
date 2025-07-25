:: load-image.bat (Windows)
@echo off
REM Launches the load-image PowerShell script.
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0load-image.ps1"
echo.
echo Press any key to close this window ...
pause > nul
